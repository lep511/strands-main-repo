"""Names shared by every Day 8 script. Override with environment variables."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REGION = os.getenv("AWS_REGION", "us-east-1")
# Sonnet on Bedrock. Adaptive-thinking Sonnet models reject temperature/top_p, so none are set.
MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-sonnet-5-5")

PREFIX = "aoa-day08"
GATEWAY_NAME = f"{PREFIX}-gateway"
TARGET_NAME = "orders"                       # tool actions become orders___<tool>
POLICY_ENGINE_NAME = "aoa_day08_tool_policies"
TOOLS_RUNTIME_NAME = "aoa_day08_order_tools"   # MCP server on AgentCore Runtime

AGENT_ROLE = f"{PREFIX}-support-agent"       # the agent's identity (Day 5)
GATEWAY_ROLE = f"{PREFIX}-gateway-service"   # what the gateway itself may do
TOOLS_ROLE = f"{PREFIX}-order-tools-runtime"

READ_TOOLS = ["lookup_order"]
DENIED_TOOLS = ["issue_refund", "delete_account"]

HERE = Path(__file__).parent
STATE_PATH = HERE / ".state.json"


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
