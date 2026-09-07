#!/usr/bin/env python3
"""
Deploy Loan Orchestrator to Amazon Bedrock AgentCore Runtime.

No CLI, no git, no project scaffolding needed.
Just run: python3 deploy_runtime.py

What this script does:
  1. Reads MCPServerFunctionUrl from CloudFormation (= GATEWAY_URL)
  2. Packages loan_orchestrator.py + arm64 dependencies into a zip
  3. Uploads the zip to S3
  4. Creates (or updates) the AgentCore Runtime with GATEWAY_URL injected
  5. Waits for it to be READY and prints the invoke command
"""

import boto3
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────────
AGENT_NAME = "LoanOrchestrator"
REGION = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))
STACK_NAME = os.environ.get("STACK_NAME", "strands-workshop")
PYTHON_RUNTIME = "PYTHON_3_12"
ENTRY_POINT = "main.py"

DEPENDENCIES = [
    "bedrock-agentcore>=0.1.0",  # Required: provides BedrockAgentCoreApp + HTTP service contract
    "strands-agents>=0.1.0",
    "mcp>=1.0.0",
    "uvicorn>=0.20.0",           # Required: bedrock-agentcore uses uvicorn to serve on port 8080
    "boto3>=1.34.0",
    "botocore>=1.34.0",
]

# Large packages to exclude from the zip to stay under the 30s init timeout
EXCLUDE_PACKAGES = {
    # Pre-installed in AgentCore Runtime — do not bundle
    "boto3", "botocore", "s3transfer", "urllib3", "certifi",
    "charset_normalizer", "idna", "requests",
    # cryptography has a large native .so — pre-installed in Python 3.12 runtime
    "cryptography", "cffi", "pycparser",
}
# ─────────────────────────────────────────────────────────────────────────────


def get_account_id():
    sts = boto3.client("sts", region_name=REGION)
    return sts.get_caller_identity()["Account"]


def get_stack_outputs():
    cfn = boto3.client("cloudformation", region_name=REGION)
    try:
        stack = cfn.describe_stacks(StackName=STACK_NAME)["Stacks"][0]
        return {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}
    except Exception as e:
        print(f"   ⚠️  Could not read CloudFormation stack ({e})")
        return {}


def get_gateway_url(outputs, account_id):
    """Get Gateway URL: env var > gateway_info.json > stack MCPServerFunctionUrl."""
    # 1. Explicit env var
    if os.environ.get("GATEWAY_URL"):
        return os.environ["GATEWAY_URL"]
    # 2. gateway_info.json from setup_gateway.py
    gateway_file = Path(__file__).parent / "gateway_info.json"
    if gateway_file.exists():
        with open(gateway_file) as f:
            url = json.load(f).get("gateway_url", "")
        if url:
            return url
    # 3. MCPServerFunctionUrl from CloudFormation stack
    if outputs.get("MCPServerFunctionUrl"):
        return outputs["MCPServerFunctionUrl"]
    return ""


def get_execution_role(outputs, account_id):
    """Get execution role: env var > stack output > constructed name."""
    if os.environ.get("AGENTCORE_ROLE_ARN"):
        return os.environ["AGENTCORE_ROLE_ARN"]
    if outputs.get("AgentCoreRoleArn"):
        return outputs["AgentCoreRoleArn"]
    # Construct from known naming convention
    return f"arn:aws:iam::{account_id}:role/strands-loan-workshop-strands-agent-role"


def ensure_s3_bucket(s3_client, bucket_name, account_id):
    """Create S3 bucket if it doesn't exist."""
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        print(f"   ✅ S3 bucket exists: {bucket_name}")
    except Exception:
        print(f"   📦 Creating S3 bucket: {bucket_name}")
        if REGION == "us-east-1":
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": REGION},
            )
        print(f"   ✅ Bucket created")


def build_deployment_zip(tmp_dir, agent_source, gateway_url):
    """Package main.py + arm64 dependencies into deployment.zip"""
    package_dir = os.path.join(tmp_dir, "package")
    os.makedirs(package_dir, exist_ok=True)

    print("   📦 Installing arm64 dependencies (this takes ~2 minutes)...")
    # Use uv for reliable arm64 cross-platform installs
    result = subprocess.run(
        [
            "uv", "pip", "install",
            "--python-platform", "aarch64-manylinux2014",
            "--python-version", "3.12",
            "--target", package_dir,
            "-q",
        ] + DEPENDENCIES,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"   ⚠️  uv arm64 install failed: {result.stderr[:500]}")
        print("   ↩️  Falling back to native pip install...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "--target", package_dir, "-q"] + DEPENDENCIES,
            check=True,
        )

    # Copy loan_orchestrator.py as main.py, injecting GATEWAY_URL
    dest_main = os.path.join(package_dir, "main.py")
    with open(agent_source) as f:
        source_code = f.read()

    if gateway_url:
        # Inject GATEWAY_URL env var at module level so handler picks it up
        inject = (
            f'\n# Injected by deploy_runtime.py\n'
            f'import os as _os\n'
            f'_os.environ.setdefault("GATEWAY_URL", "{gateway_url}")\n'
        )
        # Insert after the last import line (before SYSTEM_PROMPT)
        source_code = source_code.replace("SYSTEM_PROMPT =", inject + "\nSYSTEM_PROMPT =", 1)

    with open(dest_main, "w") as f:
        f.write(source_code)

    # Create zip
    zip_path = os.path.join(tmp_dir, "deployment.zip")
    print("   🗜️  Creating deployment.zip...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(package_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            # Skip top-level excluded packages
            rel_root = os.path.relpath(root, package_dir)
            top_pkg = rel_root.split(os.sep)[0].split("-")[0].replace("_", "-").lower()
            if top_pkg in EXCLUDE_PACKAGES:
                dirs[:] = []
                continue
            for file in files:
                if file.endswith(".pyc"):
                    continue
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, package_dir)
                zf.write(abs_path, rel_path)

    zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"   ✅ deployment.zip created ({zip_size_mb:.1f} MB)")
    return zip_path


def get_or_create_runtime(client, bucket_name, s3_prefix, role_arn, gateway_url):
    """Create or update AgentCore Runtime."""
    artifact = {
        "codeConfiguration": {
            "code": {"s3": {"bucket": bucket_name, "prefix": s3_prefix}},
            "runtime": PYTHON_RUNTIME,
            "entryPoint": [ENTRY_POINT],
        }
    }

    # Check if runtime already exists — update and return early
    try:
        existing = client.list_agent_runtimes()
        for rt in existing.get("agentRuntimes", []):
            if rt["agentRuntimeName"] == AGENT_NAME:
                runtime_id = rt["agentRuntimeId"]
                print(f"   ♻️  Runtime already exists: {runtime_id} — updating code...")
                client.update_agent_runtime(
                    agentRuntimeId=runtime_id,
                    agentRuntimeArtifact=artifact,
                    roleArn=role_arn,
                    networkConfiguration={"networkMode": "PUBLIC"},
                )
                return runtime_id
    except Exception as e:
        raise RuntimeError(f"Failed to list/update runtimes: {e}") from e

    env_vars = {"GATEWAY_URL": gateway_url} if gateway_url else {}

    create_kwargs = dict(
        agentRuntimeName=AGENT_NAME,
        agentRuntimeArtifact=artifact,
        networkConfiguration={"networkMode": "PUBLIC"},
        roleArn=role_arn,
        lifecycleConfiguration={"idleRuntimeSessionTimeout": 300, "maxLifetime": 3600},
    )
    if env_vars:
        create_kwargs["environmentVariables"] = env_vars

    response = client.create_agent_runtime(**create_kwargs)
    return response["agentRuntimeId"]


def wait_for_ready(client, runtime_id, max_wait=300):
    """Poll until runtime is READY or FAILED."""
    print(f"   ⏳ Waiting for runtime to be READY (up to {max_wait}s)...")
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            resp = client.get_agent_runtime(agentRuntimeId=runtime_id)
            status = resp.get("status", "UNKNOWN")
            print(f"      Status: {status}")
            if status == "READY":
                return True
            if "FAIL" in status or "ERROR" in status:
                print(f"   ❌ Runtime failed with status: {status}")
                return False
        except Exception as e:
            print(f"      (polling error: {e})")
        time.sleep(15)
    print("   ⚠️  Timed out waiting for READY state")
    return False


def main():
    print("=" * 60)
    print("  Loan Orchestrator → AgentCore Runtime Deploy")
    print("=" * 60)

    account_id = get_account_id()
    print(f"✅ Account: {account_id}  Region: {REGION}")

    print(f"\n📋 Reading CloudFormation stack '{STACK_NAME}'...")
    outputs = get_stack_outputs()

    # Gateway URL
    gateway_url = get_gateway_url(outputs, account_id)
    if gateway_url:
        print(f"   ✅ Gateway URL: {gateway_url}")
    else:
        print("   ⚠️  No Gateway URL found. Run setup_gateway.py first or set GATEWAY_URL env var.")

    # Execution role
    role_arn = get_execution_role(outputs, account_id)
    print(f"   ✅ Execution role: {role_arn}")

    # Source file
    script_dir = Path(__file__).parent
    agent_source = script_dir / "loan_orchestrator.py"
    if not agent_source.exists():
        print(f"❌ Agent source not found: {agent_source}")
        sys.exit(1)

    # S3 setup — prefix (not key) is used by AgentCore Runtime API
    bucket_name = f"bedrock-agentcore-code-{account_id}-{REGION}"
    s3_prefix = f"{AGENT_NAME}/deployment.zip"
    s3_client = boto3.client("s3", region_name=REGION)

    print(f"\n📦 Building deployment package...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        ensure_s3_bucket(s3_client, bucket_name, account_id)

        zip_path = build_deployment_zip(tmp_dir, agent_source, gateway_url)

        print(f"\n⬆️  Uploading to s3://{bucket_name}/{s3_prefix}...")
        s3_client.upload_file(zip_path, bucket_name, s3_prefix)
        print("   ✅ Upload complete")

    # Deploy to AgentCore Runtime
    print(f"\n🚀 Deploying to AgentCore Runtime...")
    agentcore_client = boto3.client("bedrock-agentcore-control", region_name=REGION)
    runtime_id = get_or_create_runtime(
        agentcore_client, bucket_name, s3_prefix, role_arn, gateway_url
    )
    print(f"   ✅ Runtime ID: {runtime_id}")

    ready = wait_for_ready(agentcore_client, runtime_id)

    # Save runtime info
    runtime_info = {
        "runtime_id": runtime_id,
        "region": REGION,
        "account_id": account_id,
        "gateway_url": gateway_url,
    }
    info_path = script_dir / "runtime_info.json"
    with open(info_path, "w") as f:
        json.dump(runtime_info, f, indent=2)

    account_id_short = account_id
    log_group = f"/aws/bedrock-agentcore/runtimes/{runtime_id}-DEFAULT/runtime-logs"

    print(f"\n{'=' * 60}")
    if ready:
        print("🎉 AgentCore Runtime deployed successfully!")
    else:
        print("⚠️  Runtime deployed but may still be initialising.")
    print(f"\nRuntime ID: {runtime_id}")
    print(f"Region:     {REGION}")
    print(f"Info saved: {info_path}")
    print(f"\n📊 CloudWatch Logs (after first invocation):")
    print(f"   Log group: {log_group}")
    print(f"   aws logs tail '{log_group}' --follow --region {REGION}")
    print(f"\nTo invoke:")
    arn = f"arn:aws:bedrock-agentcore:{REGION}:{account_id}:runtime/{runtime_id}"
    print(f'  python3 -c "')
    print(f'import boto3, json')
    print(f'client = boto3.client(\"bedrock-agentcore\", region_name=\"{REGION}\")')
    print(f'resp = client.invoke_agent_runtime(')
    print(f'    agentRuntimeArn=\"{arn}\",')
    print(f'    qualifier=\"DEFAULT\",')
    print(f'    payload=json.dumps({{\"query\": \"Process a loan for John Smith, phone 07700900000, GBP 1500 over 30 days\"}}).encode()')
    print(f')')
    print(f'print(resp[\"response\"].read().decode())')
    print(f'"')
    print("=" * 60)


if __name__ == "__main__":
    main()
