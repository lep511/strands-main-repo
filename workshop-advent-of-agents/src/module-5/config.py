"""Names shared by every Day 5 script. Override with environment variables."""

import json
import os
from functools import cache
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv()

REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-sonnet-5")

AGENT_NAME = os.getenv("AGENT_NAME", "aoa_day05_weather")  # [a-zA-Z][a-zA-Z0-9_]{0,47}
ROLE_NAME = f"AmazonBedrockAgentCore-{AGENT_NAME}"           # one role per agent, never shared
GRANT_POLICY_NAME = "aoa-day05-athena-read"

GLUE_DATABASE = "sample_data"
TABLE = "cities_weather"
ATHENA_WORKGROUP = "aoa-day05"

HERE = Path(__file__).parent
STATE_PATH = HERE / ".state.json"


@cache
def account_id() -> str:
    return boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]


def bucket() -> str:
    return os.getenv("AOA_BUCKET", f"aoa-day05-{account_id()}-{REGION}")


def load_state() -> dict:
    return json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}


def save_state(**values) -> dict:
    state = load_state() | values
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str))
    return state


def require_state(key: str) -> str:
    state = load_state()
    if key not in state:
        raise SystemExit(f"'{key}' not found in {STATE_PATH.name}: run deploy.py first.")
    return state[key]
