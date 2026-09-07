#!/usr/bin/env python3
"""
Deploy Loan Orchestrator to AgentCore Runtime.

Usage:
    python3 deploy_to_agentcore.py
"""
from bedrock_agentcore_starter_toolkit import Runtime
import boto3
import json
import os
from pathlib import Path

REGION = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))
STACK_NAME = os.environ.get("STACK_NAME", "strands-workshop")
AGENT_NAME = "LoanOrchestrator"

# Get account ID
sts = boto3.client("sts", region_name=REGION)
account_id = sts.get_caller_identity()["Account"]

# Get execution role from CloudFormation stack
cfn = boto3.client("cloudformation", region_name=REGION)
stack = cfn.describe_stacks(StackName=STACK_NAME)["Stacks"][0]
outputs = {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}
execution_role = outputs.get("AgentCoreRoleArn", f"arn:aws:iam::{account_id}:role/strands-loan-workshop-strands-agent-role")

# Get gateway URL
gateway_info = json.loads(Path("gateway_info.json").read_text())
gateway_url = gateway_info["gateway_url"]

print("🚀 Deploying Loan Orchestrator to AgentCore Runtime...\n")
print(f"   Account:     {account_id}")
print(f"   Region:      {REGION}")
print(f"   Role:        {execution_role}")
print(f"   Gateway URL: {gateway_url}\n")

runtime = Runtime()

runtime.configure(
    entrypoint="loan_orchestrator.py",
    execution_role=execution_role,
    auto_create_ecr=True,
    requirements_file="requirements.txt",
    region=REGION,
    agent_name=AGENT_NAME,
)

launch_result = runtime.launch(
    auto_update_on_conflict=True,
    env_vars={"GATEWAY_URL": gateway_url},
)

# Save runtime info for the UI
info = {
    "runtime_id": launch_result.agent_arn.split("/")[-1],
    "region": REGION,
    "account_id": account_id,
    "gateway_url": gateway_url,
}
Path("runtime_info.json").write_text(json.dumps(info, indent=2))

print(f"\n✅ Deployed successfully!")
print(f"   Agent ARN: {launch_result.agent_arn}")
print(f"\n   To start the UI: python3 app.py")
