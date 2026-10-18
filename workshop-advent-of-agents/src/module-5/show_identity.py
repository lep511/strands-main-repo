"""STEP 9: confirm the agent has an identity of its own, and that it can reach nothing yet.

AWS equivalent of reading `spec.effectiveIdentity`:
  * roleArn               - the IAM principal the agent's AWS calls are signed with
  * workloadIdentityArn   - the agent's AgentCore Identity (used for OAuth / API keys, Day 6)

Usage:
    uv run src/module-5/show_identity.py
"""

import json

import boto3

from config import REGION, ROLE_NAME, require_state

control = boto3.client("bedrock-agentcore-control", region_name=REGION)
iam = boto3.client("iam")


def main() -> None:
    runtime = control.get_agent_runtime(agentRuntimeId=require_state("runtime_id"))
    print(f"agent runtime        {runtime['agentRuntimeArn']}")
    print(f"execution role       {runtime['roleArn']}")
    print(f"workload identity    {runtime.get('workloadIdentityDetails', {}).get('workloadIdentityArn')}")

    role = iam.get_role(RoleName=ROLE_NAME)["Role"]
    trust = role["AssumeRolePolicyDocument"]["Statement"][0]
    print(f"\ntrusted principal    {trust['Principal']}")
    print(f"trust condition      {json.dumps(trust.get('Condition'))}")

    attached = iam.list_attached_role_policies(RoleName=ROLE_NAME)["AttachedPolicies"]
    print(f"\nmanaged policies     {[p['PolicyName'] for p in attached] or 'none'}")
    for name in iam.list_role_policies(RoleName=ROLE_NAME)["PolicyNames"]:
        doc = iam.get_role_policy(RoleName=ROLE_NAME, PolicyName=name)["PolicyDocument"]
        actions = sorted({a for s in doc["Statement"] for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])})
        print(f"inline '{name}': {', '.join(actions)}")

    data_actions = [n for n in iam.list_role_policies(RoleName=ROLE_NAME)["PolicyNames"] if n != "agentcore-baseline"]
    print("\ndata access          " + (f"granted via {data_actions}" if data_actions else "NONE (expected before STEP 11)"))


if __name__ == "__main__":
    main()
