"""Audit: who fetched which user's token? (~ RetrieveCredentials entries attributed to the agent)

Looks up the AgentCore Identity calls in CloudTrail Event history and prints, for each,
the IAM principal that called (the agent / app identity) and the workload + user involved.

Usage:
    uv run src/module-6/who_fetched.py            # last 3 hours
"""

import json
from datetime import UTC, datetime, timedelta

import boto3
from botocore.exceptions import ClientError

from config import REGION

EVENT_NAMES = [
    "GetWorkloadAccessTokenForUserId",
    "GetWorkloadAccessTokenForJWT",
    "GetResourceOauth2Token",
    "CompleteResourceTokenAuth",
]

cloudtrail = boto3.client("cloudtrail", region_name=REGION)


def lookup(since: datetime) -> list[dict]:
    rows = []
    for name in EVENT_NAMES:
        pages = cloudtrail.get_paginator("lookup_events").paginate(
            LookupAttributes=[{"AttributeKey": "EventName", "AttributeValue": name}], StartTime=since
        )
        for page in pages:
            rows += [json.loads(e["CloudTrailEvent"]) for e in page["Events"]]
    return rows


def main() -> None:
    try:
        rows = lookup(datetime.now(UTC) - timedelta(hours=3))
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "AccessDeniedException":
            raise
        raise SystemExit(
            "Your role lacks cloudtrail:LookupEvents (common in workshop accounts). Ask for it, or use the console:\n"
            "  CloudTrail -> Event history -> Event source = bedrock-agentcore.amazonaws.com"
        ) from None

    if not rows:
        print("no AgentCore Identity events yet (CloudTrail can take ~5 minutes)")
    for e in sorted(rows, key=lambda d: d["eventTime"]):
        params = e.get("requestParameters") or {}
        context = {k: v for k, v in params.items() if k in {"workloadName", "userId", "resourceCredentialProviderName", "oauth2Flow"}}
        print(f"{e['eventTime']}  {e['eventName']:<32} {e.get('errorCode') or 'OK':<14} {e['userIdentity'].get('arn')}")
        if context:
            print(f"{'':>22}{json.dumps(context)}")


if __name__ == "__main__":
    main()
