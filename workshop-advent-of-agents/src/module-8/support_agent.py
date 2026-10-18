"""The governed customer support agent (Strands + Sonnet), calling tools through the gateway.

Two ways to wire the tools, both signed AS THE AGENT'S IDENTITY:
  * default  - like the original: lookup_order, issue_refund and delete_account are defined
               in code and each posts tools/call to the gateway. The model CAN try a refund;
               the gateway policy refuses it.
  * --mcp    - Strands MCPClient on the gateway URL. Policy-aware discovery: the agent is
               only ever shown the tools it is permitted to call.

Usage:
    uv run src/module-8/support_agent.py "Where is my order ORD-1001?"
    uv run src/module-8/support_agent.py "Refund order ORD-1001 in full, it arrived broken."
    uv run src/module-8/support_agent.py --mcp "Refund ORD-1001 and delete account C-501."
"""

import argparse
import json

from strands import Agent, tool
from strands.models import BedrockModel

from config import MODEL_ID, REGION, TARGET_NAME
from gateway_client import agent_session, mcp_client, raw_tool_call

INSTRUCTION = """You are a customer service support agent. Help customers verify order statuses.
If a tool returns an error or is blocked, tell the customer plainly that you cannot do it
and that a human will follow up. Never claim an action happened unless a tool confirmed it."""

SESSION = None


def _call(tool_name: str, arguments: dict) -> dict:
    status, body = raw_tool_call(SESSION, f"{TARGET_NAME}___{tool_name}", arguments)
    if "error" in body:
        return {"status": "BLOCKED_BY_AGENTCORE_GATEWAY", "http_status": status, "error": body["error"].get("message")}
    return {"status": "OK", "result": [c.get("text") for c in body.get("result", {}).get("content", [])]}


@tool
def lookup_order(order_id: str) -> dict:
    """Check order status and tracking details.

    Args:
        order_id: Order id, e.g. ORD-1001.
    """
    return _call("lookup_order", {"order_id": order_id})


@tool
def issue_refund(order_id: str, amount: float, reason: str = "Customer Request") -> dict:
    """CRITICAL: Process a monetary refund through the protected order service.

    Args:
        order_id: Order id.
        amount: Amount to refund.
        reason: Why.
    """
    return _call("issue_refund", {"order_id": order_id, "amount": amount, "reason": reason})


@tool
def delete_account(customer_id: str) -> dict:
    """CRITICAL: Permanently delete a customer record through the protected order service.

    Args:
        customer_id: Customer id, e.g. C-501.
    """
    return _call("delete_account", {"customer_id": customer_id})


def build_agent(use_mcp: bool = False) -> Agent:
    global SESSION
    SESSION = agent_session()
    tools = [mcp_client(SESSION)] if use_mcp else [lookup_order, issue_refund, delete_account]
    return Agent(
        name="customer_support_agent",
        # The model is called with the agent's identity too.
        model=BedrockModel(model_id=MODEL_ID, region_name=REGION, boto_session=SESSION),
        system_prompt=INSTRUCTION,
        tools=tools,
        callback_handler=None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Governed support agent")
    parser.add_argument("prompt", nargs="?", default="Where is my order ORD-1001?")
    parser.add_argument("--mcp", action="store_true", help="discover tools from the gateway (policy-filtered)")
    args = parser.parse_args()

    agent = build_agent(use_mcp=args.mcp)
    print(f"tools offered to the model: {agent.tool_names}\n")
    print(f"🧑 {args.prompt}\n")
    result = agent(args.prompt)
    print(f"🤖 {str(result).strip()}\n")
    for message in agent.messages:
        for block in message["content"]:
            if "toolUse" in block:
                print(f"  [tool_call] {block['toolUse']['name']}({json.dumps(block['toolUse']['input'])})")
            if "toolResult" in block:
                text = json.dumps(block["toolResult"]["content"])[:160]
                print(f"  [result]    {text}")


if __name__ == "__main__":
    main()
