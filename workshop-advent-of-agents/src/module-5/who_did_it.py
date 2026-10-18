"""STEP 13: prove which agent made the call, from CloudTrail.

Athena API calls are CloudTrail management events, so they show up in Event history
with no trail to configure. `userIdentity.arn` names the agent's own role:
    arn:aws:sts::<account>:assumed-role/AmazonBedrockAgentCore-aoa_day05_weather/<session>

CloudTrail can take ~5 minutes to show new events; use --wait to poll.

Usage:
    uv run src/module-5/who_did_it.py
    uv run src/module-5/who_did_it.py --wait
"""

import json
import sys
import time
from datetime import UTC, datetime, timedelta

import boto3

from config import ROLE_NAME, REGION, ATHENA_WORKGROUP

cloudtrail = boto3.client("cloudtrail", region_name=REGION)
EVENTS = ["StartQueryExecution", "ListTableMetadata"]


def agent_events(since: datetime) -> list[dict]:
    found = []
    for name in EVENTS:
        pages = cloudtrail.get_paginator("lookup_events").paginate(
            LookupAttributes=[{"AttributeKey": "EventName", "AttributeValue": name}], StartTime=since
        )
        for page in pages:
            for event in page["Events"]:
                detail = json.loads(event["CloudTrailEvent"])
                params = detail.get("requestParameters") or {}
                if name == "StartQueryExecution" and params.get("workGroup") != ATHENA_WORKGROUP:
                    continue
                found.append(detail)
    return sorted(found, key=lambda d: d["eventTime"])


def main() -> None:
    since = datetime.now(UTC) - timedelta(hours=3)
    deadline = time.time() + (600 if "--wait" in sys.argv else 0)
    while True:
        events = agent_events(since)
        if any(f"assumed-role/{ROLE_NAME}/" in e["userIdentity"].get("arn", "") for e in events) or time.time() > deadline:
            break
        print("no agent events yet, retrying in 30s (CloudTrail delivery delay)...")
        time.sleep(30)

    for e in events:
        principal = e["userIdentity"].get("arn", "?")
        who = "AGENT" if f"assumed-role/{ROLE_NAME}/" in principal else "other"
        outcome = e.get("errorCode") or "OK"
        query = ((e.get("requestParameters") or {}).get("queryString") or "").split("\n")[0][:60]
        print(f"{e['eventTime']}  {e['eventName']:<20} {outcome:<22} {who:<5} {principal}")
        if query:
            print(f"{'':>22}query: {query}")


if __name__ == "__main__":
    main()
