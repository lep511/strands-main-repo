"""STEPS 10 and 12: prompt the deployed agent (the AWS equivalent of the Playground).

Usage:
    uv run src/module-5/invoke.py
    uv run src/module-5/invoke.py "Which AWS identity are you running as?"
"""

import json
import sys
import uuid

import boto3

from config import GLUE_DATABASE, REGION, TABLE, require_state

DEFAULT_PROMPT = f"Run a SQL query on {GLUE_DATABASE}.{TABLE} to return all rows"

client = boto3.client("bedrock-agentcore", region_name=REGION)


def invoke(prompt: str) -> dict:
    response = client.invoke_agent_runtime(
        agentRuntimeArn=require_state("runtime_arn"),
        runtimeSessionId=f"aoa-day05-{uuid.uuid4()}",  # >= 33 chars
        payload=json.dumps({"prompt": prompt}).encode(),
        qualifier="DEFAULT",
    )
    return json.loads(response["response"].read())


def main() -> None:
    prompt = " ".join(sys.argv[1:]) or DEFAULT_PROMPT
    print(f"🧑 {prompt}\n")
    answer = invoke(prompt)
    print(f"🤖 {answer['result']}\n")
    print(f"tools used: {answer.get('tools_used')}")


if __name__ == "__main__":
    main()
