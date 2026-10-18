"""Deploy the Day 8 boundary (~ deploy_gcp.sh of the original), idempotently.

1. Order tools MCP server (lookup_order, issue_refund, delete_account) on AgentCore Runtime.
2. The agent's own IAM role (its Day 5 identity), assumable by you for this demo.
3. A policy engine with the Cedar permit + forbid pair.
4. An AgentCore Gateway (AWS_IAM inbound auth, policy engine in ENFORCE mode) with the
   MCP server registered as target "orders" (tools become orders___<tool>). The gateway
   signs its calls to the server with SigV4 as its own service role.

Usage:
    uv run src/module-8/deploy.py
    uv run src/module-8/deploy.py --mode LOG_ONLY    # observe decisions without blocking
"""

import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.parse
import zipfile
from pathlib import Path

import boto3

import cedar_policies
from config import (
    AGENT_ROLE, DENIED_TOOLS, GATEWAY_NAME, GATEWAY_ROLE, HERE, MODEL_ID, POLICY_ENGINE_NAME, REGION,
    TARGET_NAME, TOOLS_ROLE, TOOLS_RUNTIME_NAME, save_state,
)

sts = boto3.client("sts", region_name=REGION)
iam = boto3.client("iam")
s3 = boto3.client("s3", region_name=REGION)
control = boto3.client("bedrock-agentcore-control", region_name=REGION)

ACCOUNT = sts.get_caller_identity()["Account"]
BUCKET = os.getenv("AOA_BUCKET", f"aoa-day08-{ACCOUNT}-{REGION}")
BUILD = HERE / "build"
TAGS = {"workshop": "advent-of-agents", "day": "08"}


def wait(get, label: str, done=("READY", "ACTIVE")) -> dict:
    while True:
        item = get()
        status = item.get("status", "")
        if status in done:
            return item
        if "FAIL" in status:
            raise SystemExit(f"{label} {status}: {item.get('statusReasons') or item.get('failureReason')}")
        print(f"  {label}: {status}...")
        time.sleep(5)


def ensure_role(name: str, trust: dict, inline: dict | None = None, managed: list[str] = ()) -> str:
    try:
        arn = iam.create_role(
            RoleName=name, AssumeRolePolicyDocument=json.dumps(trust),
            Tags=[{"Key": k, "Value": v} for k, v in TAGS.items()],
        )["Role"]["Arn"]
        print(f"created role {name}")
        created = True
    except iam.exceptions.EntityAlreadyExistsException:
        try:
            iam.update_assume_role_policy(RoleName=name, PolicyDocument=json.dumps(trust))
        except iam.exceptions.ClientError as exc:  # sandbox accounts may forbid it; keep the existing trust
            print(f"  keeping existing trust policy of {name} ({exc.response['Error']['Code']})")
        arn = iam.get_role(RoleName=name)["Role"]["Arn"]
        created = False
    if inline:
        managed = [*managed, ensure_managed_policy(f"{name}-permissions", inline)]
    for policy_arn in managed:
        iam.attach_role_policy(RoleName=name, PolicyArn=policy_arn)
    if created:
        time.sleep(12)  # IAM propagation
    return arn


def ensure_managed_policy(name: str, document: dict) -> str:
    """Customer-managed policy (some sandbox accounts forbid inline role policies)."""
    arn = f"arn:aws:iam::{ACCOUNT}:policy/{name}"
    try:
        iam.create_policy(PolicyName=name, PolicyDocument=json.dumps(document), Description="Advent of Agents Day 8")
    except iam.exceptions.EntityAlreadyExistsException:
        versions = iam.list_policy_versions(PolicyArn=arn)["Versions"]
        for old in sorted((v for v in versions if not v["IsDefaultVersion"]), key=lambda v: v["CreateDate"])[: max(0, len(versions) - 4)]:
            iam.delete_policy_version(PolicyArn=arn, VersionId=old["VersionId"])
        iam.create_policy_version(PolicyArn=arn, PolicyDocument=json.dumps(document), SetAsDefault=True)
    return arn


def operator_role_arn() -> str:
    """The role YOU are using; only it may assume the agent role in this demo."""
    caller = sts.get_caller_identity()["Arn"]
    if ":assumed-role/" not in caller:
        return caller  # an IAM user
    role_name = caller.split(":assumed-role/")[1].split("/")[0]
    try:
        return iam.get_role(RoleName=role_name)["Role"]["Arn"]
    except Exception:
        return f"arn:aws:iam::{ACCOUNT}:role/{role_name}"


def build_tools_package() -> Path:
    """arm64 zip of tools_server/ with mcp<2, for AgentCore Runtime direct code deployment."""
    package, zip_path = BUILD / "package", BUILD / "order_tools.zip"
    shutil.rmtree(BUILD, ignore_errors=True)
    package.mkdir(parents=True)
    subprocess.run(
        ["uv", "pip", "install", "--quiet", "--python-platform", "aarch64-manylinux2014", "--python-version", "3.13",
         "--only-binary=:all:", "--target", str(package), "-r", str(HERE / "tools_server" / "requirements.txt")],
        check=True, env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
    )
    for name in ("server.py", "orders.py"):
        shutil.copy(HERE / "tools_server" / name, package / name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(package.rglob("*")):
            if "__pycache__" in path.parts:
                continue
            info = zipfile.ZipInfo.from_file(path, path.relative_to(package))
            info.external_attr = (0o755 if path.is_dir() else 0o644) << 16
            zf.writestr(info, "" if path.is_dir() else path.read_bytes(), zipfile.ZIP_DEFLATED)
    print(f"packaged {zip_path.relative_to(HERE)} ({zip_path.stat().st_size / 1e6:.1f} MB)")
    return zip_path


def deploy_tools_server() -> dict:
    """The MCP server on AgentCore Runtime. Its runtime role can only write its own logs."""
    try:
        s3.create_bucket(Bucket=BUCKET)
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass
    s3.put_public_access_block(Bucket=BUCKET, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})

    arn = f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}"
    logs = f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:/aws/bedrock-agentcore/runtimes/{TOOLS_RUNTIME_NAME}-*"
    role = ensure_role(
        TOOLS_ROLE,
        {"Version": "2012-10-17", "Statement": [{
            "Effect": "Allow", "Principal": {"Service": "bedrock-agentcore.amazonaws.com"}, "Action": "sts:AssumeRole",
            "Condition": {"StringEquals": {"aws:SourceAccount": ACCOUNT}, "ArnLike": {"aws:SourceArn": f"{arn}:runtime/{TOOLS_RUNTIME_NAME}-*"}},
        }]},
        inline={"Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:DescribeLogStreams"], "Resource": logs},
            {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"], "Resource": f"{logs}:log-stream:*"},
            {"Effect": "Allow", "Action": "logs:DescribeLogGroups", "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:*"},
        ]},
    )
    key = f"code/{TOOLS_RUNTIME_NAME}/order_tools.zip"
    s3.upload_file(str(build_tools_package()), BUCKET, key, ExtraArgs={"ExpectedBucketOwner": ACCOUNT})
    spec = {
        "agentRuntimeArtifact": {"codeConfiguration": {
            "code": {"s3": {"bucket": BUCKET, "prefix": key}}, "runtime": "PYTHON_3_13", "entryPoint": ["server.py"]}},
        "roleArn": role,
        "networkConfiguration": {"networkMode": "PUBLIC"},
        "protocolConfiguration": {"serverProtocol": "MCP"},
    }
    found = find(control.list_agent_runtimes, "agentRuntimes", TOOLS_RUNTIME_NAME, "agentRuntimeName")
    if found:
        runtime_id = found["agentRuntimeId"]
        control.update_agent_runtime(agentRuntimeId=runtime_id, **spec)
    else:
        runtime_id = control.create_agent_runtime(agentRuntimeName=TOOLS_RUNTIME_NAME, **spec)["agentRuntimeId"]
    print(f"{'updated' if found else 'created'} MCP server runtime {runtime_id}")
    runtime = wait(lambda: control.get_agent_runtime(agentRuntimeId=runtime_id), "tools runtime")
    escaped = urllib.parse.quote(runtime["agentRuntimeArn"], safe="")
    runtime["mcpEndpoint"] = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{escaped}/invocations?qualifier=DEFAULT"
    return runtime


def find(list_call, key: str, name: str, name_key: str = "name") -> dict | None:
    for item in list_call()[key]:
        if item.get(name_key) == name:
            return item
    return None


def ensure_policy_engine() -> dict:
    found = find(control.list_policy_engines, "policyEngines", POLICY_ENGINE_NAME)
    engine_id = found["policyEngineId"] if found else control.create_policy_engine(
        name=POLICY_ENGINE_NAME, description="Day 8 tool deny rules"
    )["policyEngineId"]
    print(f"{'found' if found else 'created'} policy engine {engine_id}")
    return wait(lambda: control.get_policy_engine(policyEngineId=engine_id), "policy engine")


def ensure_gateway(role_arn: str, engine_arn: str, mode: str) -> dict:
    found = find(control.list_gateways, "items", GATEWAY_NAME)
    config = {
        "roleArn": role_arn,
        "protocolType": "MCP",
        "authorizerType": "AWS_IAM",
        "policyEngineConfiguration": {"arn": engine_arn, "mode": mode},
        "exceptionLevel": "DEBUG",
        "description": "Advent of Agents Day 8 - tool boundary",
    }
    if found:
        gateway_id = found["gatewayId"]
        control.update_gateway(gatewayIdentifier=gateway_id, name=GATEWAY_NAME, **config)
        print(f"updated gateway {gateway_id} (policy mode {mode})")
    else:
        gateway_id = control.create_gateway(name=GATEWAY_NAME, tags=TAGS, **config)["gatewayId"]
        print(f"created gateway {gateway_id} (policy mode {mode})")
    return wait(lambda: control.get_gateway(gatewayIdentifier=gateway_id), "gateway")


def ensure_target(gateway_id: str, mcp_endpoint: str) -> dict:
    found = find(lambda: control.list_gateway_targets(gatewayIdentifier=gateway_id), "items", TARGET_NAME)
    spec = {
        "targetConfiguration": {"mcp": {"mcpServer": {"endpoint": mcp_endpoint}}},
        # The gateway signs calls to the MCP server with SigV4, as its own service role.
        "credentialProviderConfigurations": [{
            "credentialProviderType": "GATEWAY_IAM_ROLE",
            "credentialProvider": {"iamCredentialProvider": {"service": "bedrock-agentcore", "region": REGION}},
        }],
    }
    if found:
        target_id = found["targetId"]
        control.update_gateway_target(gatewayIdentifier=gateway_id, targetId=target_id, name=TARGET_NAME, **spec)
    else:
        target_id = control.create_gateway_target(gatewayIdentifier=gateway_id, name=TARGET_NAME, **spec)["targetId"]
    print(f"{'updated' if found else 'created'} target {TARGET_NAME} ({target_id})")
    return wait(lambda: control.get_gateway_target(gatewayIdentifier=gateway_id, targetId=target_id), "target")


def ensure_policies(engine_id: str, gateway_arn: str) -> list[str]:
    existing = {p["name"]: p["policyId"] for p in control.list_policies(policyEngineId=engine_id)["policies"]}
    ids = []
    for name, statement in cedar_policies.policy_set(ACCOUNT, gateway_arn, AGENT_ROLE, TARGET_NAME, DENIED_TOOLS).items():
        definition = {"cedar": {"statement": statement}}
        if name in existing:
            policy_id = existing[name]
            control.update_policy(policyEngineId=engine_id, policyId=policy_id, definition=definition)
        else:
            policy_id = control.create_policy(
                policyEngineId=engine_id, name=name, definition=definition, validationMode="FAIL_ON_ANY_FINDINGS"
            )["policyId"]
        print(f"{'updated' if name in existing else 'created'} policy {name}")
        wait(lambda: control.get_policy(policyEngineId=engine_id, policyId=policy_id), f"policy {name}")
        ids.append(policy_id)
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy the Day 8 gateway boundary")
    parser.add_argument("--mode", choices=["ENFORCE", "LOG_ONLY"], default="ENFORCE")
    args = parser.parse_args()

    tools = deploy_tools_server()
    engine = ensure_policy_engine()

    arn = f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}"
    gateway_role = ensure_role(
        GATEWAY_ROLE,
        {"Version": "2012-10-17", "Statement": [{
            "Effect": "Allow", "Principal": {"Service": "bedrock-agentcore.amazonaws.com"}, "Action": "sts:AssumeRole",
            "Condition": {"StringEquals": {"aws:SourceAccount": ACCOUNT}, "ArnLike": {"aws:SourceArn": f"{arn}:gateway/{GATEWAY_NAME}-*"}},
        }]},
        inline={"Version": "2012-10-17", "Statement": [
            {"Sid": "InvokeOrderToolsServer", "Effect": "Allow", "Action": "bedrock-agentcore:InvokeAgentRuntime",
             "Resource": [tools["agentRuntimeArn"], f"{tools['agentRuntimeArn']}/*"]},
            {"Sid": "PolicyEngineConfiguration", "Effect": "Allow", "Action": "bedrock-agentcore:GetPolicyEngine", "Resource": engine["policyEngineArn"]},
            {"Sid": "PolicyEngineAuthorization", "Effect": "Allow",
             "Action": ["bedrock-agentcore:AuthorizeAction", "bedrock-agentcore:PartiallyAuthorizeActions"],
             "Resource": [engine["policyEngineArn"], f"{arn}:gateway/{GATEWAY_NAME}-*"]},
        ]},
    )
    gateway = ensure_gateway(gateway_role, engine["policyEngineArn"], args.mode)
    target = ensure_target(gateway["gatewayId"], tools["mcpEndpoint"])

    agent_role = ensure_role(
        AGENT_ROLE,
        {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"AWS": operator_role_arn()}, "Action": "sts:AssumeRole"}]},
        inline={"Version": "2012-10-17", "Statement": [
            {"Sid": "CallOnlyThisGateway", "Effect": "Allow", "Action": "bedrock-agentcore:InvokeGateway", "Resource": gateway["gatewayArn"]},
            {"Sid": "UseTheModel", "Effect": "Allow", "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
             "Resource": ["arn:aws:bedrock:*::foundation-model/*", f"arn:aws:bedrock:{REGION}:{ACCOUNT}:inference-profile/*"]},
        ]},
    )

    ensure_policies(engine["policyEngineId"], gateway["gatewayArn"])
    state = save_state(
        gateway_id=gateway["gatewayId"], gateway_arn=gateway["gatewayArn"], gateway_url=gateway["gatewayUrl"],
        target_id=target["targetId"], policy_engine_id=engine["policyEngineId"],
        tools_runtime_id=tools["agentRuntimeId"], tools_runtime_arn=tools["agentRuntimeArn"], bucket=BUCKET,
        agent_role_arn=agent_role, policy_mode=args.mode, model_id=MODEL_ID,
    )
    print("\nREADY\n" + json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
