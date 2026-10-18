"""STEPS 10-11: allow a principal to fetch user tokens for this workload from this provider.

~ `roles/agentidentity.user` on the auth provider. Grant it to:
  * the agent's execution role (STEP 10), e.g. the Day 5 role, and
  * your own role for local runs (STEP 11), otherwise GetResourceOauth2Token returns AccessDenied.

Usage:
    uv run src/module-6/grant.py --role AmazonBedrockAgentCore-aoa_day05_weather
    uv run src/module-6/grant.py --role MyDeveloperRole
    uv run src/module-6/grant.py --role MyDeveloperRole --revoke
    uv run src/module-6/grant.py --print     # just print the policy JSON
"""

import argparse
import json

import boto3

import policies
from config import PROVIDER_NAME, REGION, WORKLOAD_NAME

POLICY_NAME = "aoa-day06-delegation"


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant on-behalf-of token access")
    parser.add_argument("--role", help="IAM role name to grant")
    parser.add_argument("--revoke", action="store_true")
    parser.add_argument("--print", action="store_true", help="print the policy and exit")
    args = parser.parse_args()

    account = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]
    doc = policies.delegation_policy(account, REGION, WORKLOAD_NAME, PROVIDER_NAME)
    if args.print or not args.role:
        print(json.dumps(doc, indent=2))
        return

    iam = boto3.client("iam")
    if args.revoke:
        iam.delete_role_policy(RoleName=args.role, PolicyName=POLICY_NAME)
        print(f"revoked {POLICY_NAME} from {args.role}")
    else:
        iam.put_role_policy(RoleName=args.role, PolicyName=POLICY_NAME, PolicyDocument=json.dumps(doc))
        print(f"granted {POLICY_NAME} to {args.role}")


if __name__ == "__main__":
    main()
