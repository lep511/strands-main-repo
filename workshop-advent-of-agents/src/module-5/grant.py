"""STEP 11: grant data access to the AGENT's identity, not to a shared account.

Attaches a least-privilege inline policy (one workgroup, one database, one S3 prefix)
to this agent's execution role. Every other agent in the account is unaffected.

Usage:
    uv run src/module-5/grant.py            # grant
    uv run src/module-5/grant.py --revoke   # take it away again
"""

import json
import sys
import time

import boto3

import policies
from config import ATHENA_WORKGROUP, GLUE_DATABASE, GRANT_POLICY_NAME, REGION, ROLE_NAME, account_id, bucket

iam = boto3.client("iam")
PROPAGATION_SECONDS = 15


def main() -> None:
    if "--revoke" in sys.argv:
        iam.delete_role_policy(RoleName=ROLE_NAME, PolicyName=GRANT_POLICY_NAME)
        print(f"revoked '{GRANT_POLICY_NAME}' from {ROLE_NAME}")
    else:
        doc = policies.athena_read_policy(account_id(), REGION, bucket(), ATHENA_WORKGROUP, GLUE_DATABASE)
        iam.put_role_policy(RoleName=ROLE_NAME, PolicyName=GRANT_POLICY_NAME, PolicyDocument=json.dumps(doc))
        print(f"granted '{GRANT_POLICY_NAME}' to {ROLE_NAME}:")
        for statement in doc["Statement"]:
            print(f"  {statement['Sid']:<26} {statement['Action']}")
    print(f"waiting {PROPAGATION_SECONDS}s for IAM propagation...")
    time.sleep(PROPAGATION_SECONDS)


if __name__ == "__main__":
    main()
