"""Delete the Day 6 credential provider (and its stored secret + user tokens) and workload identity.

Usage:
    uv run src/module-6/cleanup.py
"""

import boto3

from config import PROVIDER_NAME, REGION, WORKLOAD_NAME

control = boto3.client("bedrock-agentcore-control", region_name=REGION)


def step(label: str, fn, **kwargs) -> None:
    try:
        fn(**kwargs)
        print(f"deleted {label}")
    except Exception as exc:
        print(f"skip    {label}: {type(exc).__name__}")


def main() -> None:
    step(f"credential provider {PROVIDER_NAME}", control.delete_oauth2_credential_provider, name=PROVIDER_NAME)
    step(f"workload identity {WORKLOAD_NAME}", control.delete_workload_identity, name=WORKLOAD_NAME)
    print("IAM grants are removed with: uv run src/module-6/grant.py --role <ROLE> --revoke")


if __name__ == "__main__":
    main()
