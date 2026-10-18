"""STEPS 1-4: give the agent an identity of its own, then deploy it to AgentCore Runtime.

1. Create an IAM execution role dedicated to THIS agent. Its trust policy lets only
   AgentCore assume it, and only for runtimes named after this agent.
2. Attach the baseline policy (logs, traces, model, own workload token). No data access.
3. Package agent/ for arm64 with uv and upload it (direct code deployment).
4. Create or update the runtime. AgentCore also mints a workload identity for it.

Usage:
    uv run src/module-5/deploy.py
"""

import json
import os
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

import boto3

import policies
from setup_data import create_bucket
from config import (
    AGENT_NAME, ATHENA_WORKGROUP, GLUE_DATABASE, HERE, MODEL_ID, REGION, ROLE_NAME,
    account_id, bucket, save_state,
)

BUILD = HERE / "build"
PACKAGE = BUILD / "package"
ZIP_PATH = BUILD / "deployment_package.zip"
CODE_KEY = f"code/{AGENT_NAME}/deployment_package.zip"

iam = boto3.client("iam")
s3 = boto3.client("s3", region_name=REGION)
control = boto3.client("bedrock-agentcore-control", region_name=REGION)


def ensure_role() -> str:
    account = account_id()
    trust = json.dumps(policies.trust_policy(account, REGION, AGENT_NAME))
    try:
        arn = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=trust,
            Description=f"Execution identity for agent {AGENT_NAME} only (Advent of Agents Day 5)",
            Tags=[{"Key": "agent", "Value": AGENT_NAME}, {"Key": "workshop", "Value": "advent-of-agents"}],
        )["Role"]["Arn"]
        print(f"created role {arn}")
        created = True
    except iam.exceptions.EntityAlreadyExistsException:
        iam.update_assume_role_policy(RoleName=ROLE_NAME, PolicyDocument=trust)
        arn = iam.get_role(RoleName=ROLE_NAME)["Role"]["Arn"]
        print(f"role exists {arn}")
        created = False

    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="agentcore-baseline",
        PolicyDocument=json.dumps(policies.baseline_policy(account, REGION, AGENT_NAME)),
    )
    if created:
        print("waiting 15s for IAM propagation...")
        time.sleep(15)
    return arn


def build_package() -> Path:
    shutil.rmtree(BUILD, ignore_errors=True)
    PACKAGE.mkdir(parents=True)
    subprocess.run(
        [
            "uv", "pip", "install", "--quiet",
            "--python-platform", "aarch64-manylinux2014",
            "--python-version", "3.13",
            "--only-binary=:all:",
            "--target", str(PACKAGE),
            "-r", str(HERE / "agent" / "requirements.txt"),
        ],
        check=True,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
    )
    shutil.copy(HERE / "agent" / "main.py", PACKAGE / "main.py")

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PACKAGE.rglob("*")):
            if "__pycache__" in path.parts:
                continue
            info = zipfile.ZipInfo.from_file(path, path.relative_to(PACKAGE))
            info.external_attr = (0o755 if path.is_dir() else 0o644) << 16
            if path.is_dir():
                zf.writestr(info, "")
            else:
                zf.writestr(info, path.read_bytes(), zipfile.ZIP_DEFLATED)
    print(f"packaged {ZIP_PATH.relative_to(HERE)} ({ZIP_PATH.stat().st_size / 1e6:.1f} MB)")
    return ZIP_PATH


def find_runtime_id() -> str | None:
    for page in control.get_paginator("list_agent_runtimes").paginate():
        for runtime in page["agentRuntimes"]:
            if runtime["agentRuntimeName"] == AGENT_NAME:
                return runtime["agentRuntimeId"]
    return None


def deploy(role_arn: str) -> dict:
    create_bucket(bucket())  # the same bucket later holds the Day 5 data (setup_data.py)
    s3.upload_file(str(ZIP_PATH), bucket(), CODE_KEY, ExtraArgs={"ExpectedBucketOwner": account_id()})
    print(f"uploaded s3://{bucket()}/{CODE_KEY}")

    spec = {
        "agentRuntimeArtifact": {
            "codeConfiguration": {
                "code": {"s3": {"bucket": bucket(), "prefix": CODE_KEY}},
                "runtime": "PYTHON_3_13",
                "entryPoint": ["main.py"],
            }
        },
        "roleArn": role_arn,
        "networkConfiguration": {"networkMode": "PUBLIC"},
        "environmentVariables": {
            "MODEL_ID": MODEL_ID,
            "ATHENA_WORKGROUP": ATHENA_WORKGROUP,
            "GLUE_DATABASE": GLUE_DATABASE,
        },
        "lifecycleConfiguration": {"idleRuntimeSessionTimeout": 300, "maxLifetime": 1800},
    }
    if runtime_id := find_runtime_id():
        control.update_agent_runtime(agentRuntimeId=runtime_id, **spec)
        print(f"updating runtime {runtime_id}")
    else:
        runtime_id = control.create_agent_runtime(agentRuntimeName=AGENT_NAME, **spec)["agentRuntimeId"]
        print(f"creating runtime {runtime_id}")

    while (runtime := control.get_agent_runtime(agentRuntimeId=runtime_id))["status"] not in {
        "READY", "CREATE_FAILED", "UPDATE_FAILED",
    }:
        print(f"  status {runtime['status']}...")
        time.sleep(10)
    if runtime["status"] != "READY":
        raise SystemExit(f"deploy failed: {runtime.get('failureReason')}")
    return runtime


def main() -> None:
    role_arn = ensure_role()
    build_package()
    runtime = deploy(role_arn)
    state = save_state(
        runtime_id=runtime["agentRuntimeId"],
        runtime_arn=runtime["agentRuntimeArn"],
        role_arn=runtime["roleArn"],
        workload_identity_arn=runtime.get("workloadIdentityDetails", {}).get("workloadIdentityArn"),
    )
    print("\nREADY")
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
