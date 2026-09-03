"""Dogwood Temporal Policies on Amazon Bedrock AgentCore.

Demonstrates how to deploy Dogwood temporal policies using AgentCore Policy,
which evaluates policies at the Gateway boundary on every tool call.

Architecture:
  Agent -> AgentCore Gateway -> Policy Engine (Dogwood) -> Tool (Lambda/Runtime)

The workflow:
  1. Create a policy engine
  2. Create temporal policies (Dogwood) on the engine
  3. Associate the engine with a Gateway in ENFORCE mode
  4. The Gateway evaluates temporal conditions per-session automatically

AgentCore tracks event history per session via the
x-amzn-bedrock-agentcore-policy-session-id header. Each tool call is recorded
as a request/response/error event, and temporal conditions evaluate against
that session history.

Prerequisites:
  - AWS account with AgentCore access
  - AgentCore CLI: npm install -g @aws/agentcore
  - An AgentCore Gateway with tool targets deployed
  - IAM role with bedrock-agentcore:GetWorkloadAccessToken permission

Reference:
  https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-temporal.html
  https://github.com/dogwood-policy/dogwood
"""

from __future__ import annotations

import json

import boto3
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

console = Console()

# ---------------------------------------------------------------------------
# Configuration — replace with your actual values
# ---------------------------------------------------------------------------

REGION = "us-east-1"
GATEWAY_ARN = "arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/my-gateway"
GATEWAY_TARGET_NAME = "TradingTarget"


# ---------------------------------------------------------------------------
# Helper: format a Dogwood policy for the create-policy API
# ---------------------------------------------------------------------------

def make_policy_definition(statement: str) -> dict:
    """Wrap a Dogwood policy statement for the create-policy API.

    Temporal policies use the 'policy' key (not 'cedar') in the definition.
    """
    return {"policy": {"statement": statement}}


# ---------------------------------------------------------------------------
# Policy definitions (Dogwood temporal policies for AgentCore)
# ---------------------------------------------------------------------------

# Action names follow AgentCore's convention: <TargetName>___<tool_name>
SELL_ACTION = f'AgentCore::Action::"{GATEWAY_TARGET_NAME}___sell_shares"'
APPROVE_ACTION = f'AgentCore::Action::"{GATEWAY_TARGET_NAME}___approve_sale"'
TRANSFER_ACTION = f'AgentCore::Action::"{GATEWAY_TARGET_NAME}___transfer_funds"'
BALANCE_ACTION = f'AgentCore::Action::"{GATEWAY_TARGET_NAME}___get_account_balance"'
GATEWAY_RESOURCE = f'AgentCore::Gateway::"{GATEWAY_ARN}"'


POLICIES = {
    # 1. Output-to-input integrity: sell only after approval for the same stock
    "ApproveBeforeSell": f"""permit (
    principal,
    action == {SELL_ACTION},
    resource == {GATEWAY_RESOURCE}
)
when temporal {{
    formerly within 1h {APPROVE_ACTION}::response{{
        eventResource:   resource,
        input.stock:     context.input.stock,
        input.shares:    context.input.shares,
        output.approved: true
    }}
}};""",

    # 2. Allow the approval action itself (needed so it gets recorded as response)
    "PermitApproval": f"""permit (
    principal,
    action == {APPROVE_ACTION},
    resource == {GATEWAY_RESOURCE}
);""",

    # 3. Session-based rate limiting: max 5 transfers per 5 minutes
    "RateLimitTransfers": f"""forbid (
    principal,
    action == {TRANSFER_ACTION},
    resource == {GATEWAY_RESOURCE}
)
when temporal {{
    exists (n: Long).
        (count for (t: Timepoint).
            where (formerly within 5m ({TRANSFER_ACTION}::request{{
                eventResource: resource
            }} && tp(t)))) == n
        && n > 5
}};""",

    # 4. Cumulative budget: max $10,000 in transfers per 24h
    "TransferBudget": f"""forbid (
    principal,
    action == {TRANSFER_ACTION},
    resource == {GATEWAY_RESOURCE}
)
when temporal {{
    exists (total: Long).
        (sum amt for (amt: Long), (t: Timepoint).
            where (formerly within 24h ({TRANSFER_ACTION}::request{{
                eventResource: resource, input.amount: amt
            }} && tp(t)))) == total
        && total >= 10000
}};""",

    # 5. Allow transfers (the forbid policies above override when triggered)
    "PermitTransfer": f"""permit (
    principal,
    action == {TRANSFER_ACTION},
    resource == {GATEWAY_RESOURCE}
);""",

    # 6. One-time-use approval: transfer only if no transfer since last balance check
    "OneTimeApproval": f"""permit (
    principal,
    action == {TRANSFER_ACTION},
    resource == {GATEWAY_RESOURCE}
)
when temporal {{
    !{TRANSFER_ACTION}::response{{ eventResource: resource }}
    since within 1h {BALANCE_ACTION}::response{{ eventResource: resource }}
}};""",

    # 7. Cool-down: no repeated transfer within 1 minute
    "TransferCooldown": f"""forbid (
    principal,
    action == {TRANSFER_ACTION},
    resource == {GATEWAY_RESOURCE}
)
when temporal {{
    formerly within 1m {TRANSFER_ACTION}::response{{
        eventResource: resource
    }}
}};""",
}


# ---------------------------------------------------------------------------
# Step 1: Create a policy engine
# ---------------------------------------------------------------------------

def create_policy_engine(client, name: str = "TradingPolicyEngine") -> str:
    """Create an AgentCore policy engine and return its ARN."""
    response = client.create_policy_engine(
        name=name,
        description="Dogwood temporal policies for stock trading agent",
    )
    engine_id = response["policyEngineId"]
    engine_arn = response["policyEngineArn"]
    console.print(f"  Policy Engine ID:  [bold]{engine_id}[/]")
    console.print(f"  Policy Engine ARN: [bold]{engine_arn}[/]")
    return engine_id


# ---------------------------------------------------------------------------
# Step 2: Create temporal policies on the engine
# ---------------------------------------------------------------------------

def create_policies(client, engine_id: str):
    """Create all Dogwood temporal policies on the policy engine."""
    for name, statement in POLICIES.items():
        console.print(f"\n  Creating policy: [cyan]{name}[/]")

        definition = make_policy_definition(statement)

        response = client.create_policy(
            policyEngineId=engine_id,
            name=name,
            definition=definition,
            validationMode="FAIL_ON_ANY_FINDINGS",
        )

        policy_id = response["policyId"]
        console.print(f"    Policy ID: {policy_id}")
        console.print(Syntax(statement, "cedar", theme="monokai", line_numbers=False))


# ---------------------------------------------------------------------------
# Step 3: Associate engine with Gateway (via agentcore CLI)
# ---------------------------------------------------------------------------

def show_gateway_association_instructions(engine_id: str):
    """Show CLI commands to associate the policy engine with a Gateway."""
    console.print(Panel(
        f"[bold]Associate the policy engine with your Gateway:[/]\n\n"
        f"  # Using AgentCore CLI (recommended)\n"
        f"  agentcore add policy-engine --name TradingPolicyEngine \\\n"
        f"    --attach-to-gateways MyGateway \\\n"
        f"    --attach-mode ENFORCE\n\n"
        f"  # Or update an existing gateway via AWS CLI\n"
        f"  aws bedrock-agentcore-control update-gateway \\\n"
        f"    --gateway-id <gateway-id> \\\n"
        f"    --policy-config '{{\n"
        f'      "policyEngineArn": "<engine-arn>",\n'
        f'      "mode": "ENFORCE"\n'
        f"    }}'\n\n"
        f"  # Deploy changes\n"
        f"  agentcore deploy",
        title="Gateway Association",
        border_style="yellow",
    ))


# ---------------------------------------------------------------------------
# Step 4: Invoke tools through the Gateway with session tracking
# ---------------------------------------------------------------------------

def show_invocation_example():
    """Show how to invoke tools with the temporal session header."""

    python_code = '''import boto3
import uuid

# Create a session ID for temporal policy tracking.
# The Gateway tracks events per session — temporal conditions
# evaluate against events recorded under the same session ID.
session_id = str(uuid.uuid4())

# Create the AgentCore data-plane client
client = boto3.client("bedrock-agentcore", region_name="us-east-1")

gateway_id = "my-gateway-id"
base_url = f"https://{gateway_id}.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"

# Step 1: Approve the sale (recorded as response event in session)
approve_response = client.invoke_gateway(
    gatewayId=gateway_id,
    method="tools/call",
    params={
        "name": "TradingTarget___approve_sale",
        "arguments": {"stock": "AMZN", "shares": 100},
    },
    headers={
        "x-amzn-bedrock-agentcore-policy-session-id": session_id,
    },
)
print("Approval:", approve_response)

# Step 2: Sell shares (temporal policy checks for prior approval)
sell_response = client.invoke_gateway(
    gatewayId=gateway_id,
    method="tools/call",
    params={
        "name": "TradingTarget___sell_shares",
        "arguments": {"stock": "AMZN", "shares": 100},
    },
    headers={
        "x-amzn-bedrock-agentcore-policy-session-id": session_id,
    },
)
print("Sale:", sell_response)  # ALLOWED — approval found in session

# Step 3: Try selling again without new approval
sell_again = client.invoke_gateway(
    gatewayId=gateway_id,
    method="tools/call",
    params={
        "name": "TradingTarget___sell_shares",
        "arguments": {"stock": "AMZN", "shares": 100},
    },
    headers={
        "x-amzn-bedrock-agentcore-policy-session-id": session_id,
    },
)
print("Sale again:", sell_again)  # Result depends on one-time-use policy
'''

    console.print(Panel(
        Syntax(python_code, "python", theme="monokai", line_numbers=True),
        title="[bold]Invoking Tools with Temporal Session Tracking[/]",
        border_style="green",
    ))


# ---------------------------------------------------------------------------
# Step 5: Using curl for testing
# ---------------------------------------------------------------------------

def show_curl_examples():
    """Show curl commands for testing temporal policies."""
    console.print(Panel(
        "[bold]Testing with curl:[/]\n\n"
        "  # Set your session ID (reuse across related requests)\n"
        '  SESSION_ID=$(uuidgen)\n\n'
        "  # Request 1: Approve the sale\n"
        "  curl -X POST $GATEWAY_URL/mcp \\\n"
        '    -H "Content-Type: application/json" \\\n'
        '    -H "x-amzn-bedrock-agentcore-policy-session-id: $SESSION_ID" \\\n'
        "    -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\n"
        '         "params":{"name":"TradingTarget___approve_sale",\n'
        '                   "arguments":{"stock":"AMZN","shares":100}}}\'\n\n'
        "  # Request 2: Sell shares (uses same session ID)\n"
        "  curl -X POST $GATEWAY_URL/mcp \\\n"
        '    -H "Content-Type: application/json" \\\n'
        '    -H "x-amzn-bedrock-agentcore-policy-session-id: $SESSION_ID" \\\n'
        "    -d '{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\n"
        '         "params":{"name":"TradingTarget___sell_shares",\n'
        '                   "arguments":{"stock":"AMZN","shares":100}}}\'\n\n'
        "  # Request 3: Transfer (will be rate-limited after 5 calls)\n"
        "  curl -X POST $GATEWAY_URL/mcp \\\n"
        '    -H "Content-Type: application/json" \\\n'
        '    -H "x-amzn-bedrock-agentcore-policy-session-id: $SESSION_ID" \\\n'
        "    -d '{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\n"
        '         "params":{"name":"TradingTarget___transfer_funds",\n'
        '                   "arguments":{"fromAccount":"A1","toAccount":"A2","amount":500}}}\'',
        title="curl Examples",
        border_style="cyan",
    ))


# ---------------------------------------------------------------------------
# AgentCore CLI workflow (the fastest path)
# ---------------------------------------------------------------------------

def show_cli_workflow():
    """Show the complete AgentCore CLI workflow for temporal policies."""
    console.print(Panel(
        "[bold]Complete AgentCore CLI Workflow:[/]\n\n"
        "  # 1. Create project\n"
        "  agentcore create --name TradingAgent --defaults\n"
        "  cd TradingAgent\n\n"
        "  # 2. Add gateway\n"
        "  agentcore add gateway --name TradingGateway \\\n"
        "    --authorizer-type IAM --runtimes TradingAgent\n\n"
        "  # 3. Add tool target (Lambda)\n"
        "  agentcore add gateway-target --name TradingTarget \\\n"
        "    --type lambda-function-arn \\\n"
        "    --lambda-arn $LAMBDA_ARN \\\n"
        "    --tool-schema-file trading_tools.json \\\n"
        "    --gateway TradingGateway\n\n"
        "  # 4. Add policy engine\n"
        "  agentcore add policy-engine --name TradingPolicyEngine \\\n"
        "    --attach-to-gateways TradingGateway \\\n"
        "    --attach-mode ENFORCE\n\n"
        "  # 5. First deploy (creates gateway, gets ARN)\n"
        "  agentcore deploy\n"
        "  agentcore status  # note the gateway ARN\n\n"
        "  # 6. Add temporal policies (Dogwood)\n"
        "  agentcore add policy --name ApproveBeforeSell \\\n"
        "    --engine TradingPolicyEngine \\\n"
        "    --source approve_before_sell.dw\n\n"
        "  # Or generate from natural language:\n"
        "  agentcore add policy --name RateLimit \\\n"
        "    --engine TradingPolicyEngine \\\n"
        '    --generate "Forbid transfers after 5 in 5 minutes" \\\n'
        "    --gateway TradingGateway\n\n"
        "  # 7. Redeploy with policies\n"
        "  agentcore deploy",
        title="AgentCore CLI Workflow",
        border_style="bright_blue",
    ))


# ---------------------------------------------------------------------------
# Main: display all examples
# ---------------------------------------------------------------------------

def main():
    console.print(Panel(
        "[bold]Dogwood Temporal Policies on AgentCore[/]\n\n"
        "AgentCore Policy evaluates Dogwood temporal policies at the Gateway\n"
        "boundary. The Gateway automatically tracks events per session and\n"
        "evaluates temporal conditions on every tool call.\n\n"
        "Key concepts:\n"
        "  [cyan]Policy Engine[/]  - Collection of Cedar/Dogwood policies\n"
        "  [cyan]Session ID[/]     - Groups requests; scopes temporal history\n"
        "  [cyan]Event kinds[/]    - ::request, ::response, ::error\n"
        "  [cyan]eventResource[/]  - Must be set to 'resource' in every predicate\n\n"
        "Temporal policies use the 'policy' key (not 'cedar') in create-policy.\n"
        "Standard Cedar policies continue to use 'cedar'.\n\n"
        "[dim]Docs: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-temporal.html[/]",
        title="Demo",
        border_style="bright_blue",
    ))
    console.print()

    # Show the AgentCore CLI workflow
    show_cli_workflow()
    console.print()

    # Show all temporal policies we'd create
    console.rule("[bold cyan]Temporal Policies (Dogwood)[/]")
    console.print()

    table = Table(title="Policies for Stock Trading Agent", show_lines=True)
    table.add_column("Policy", style="bold", width=22)
    table.add_column("Type", width=12)
    table.add_column("Temporal Operator", width=20)
    table.add_column("What it enforces", width=40)

    table.add_row("ApproveBeforeSell", "permit", "formerly within 1h", "Sale requires matching approval in session")
    table.add_row("PermitApproval", "permit", "— (plain Cedar)", "Allows approval calls to be recorded")
    table.add_row("RateLimitTransfers", "forbid", "count ... > 5", "Max 5 transfers per 5-minute window")
    table.add_row("TransferBudget", "forbid", "sum ... >= 10000", "Max $10,000 total transfers per 24h")
    table.add_row("PermitTransfer", "permit", "— (plain Cedar)", "Allows transfers (overridden by forbids)")
    table.add_row("OneTimeApproval", "permit", "!A since B", "Each approval good for one transfer only")
    table.add_row("TransferCooldown", "forbid", "formerly within 1m", "1-minute cool-down between transfers")

    console.print(table)
    console.print()

    # Show each policy's Dogwood source
    for name, statement in POLICIES.items():
        console.print(f"[bold cyan]{name}[/]")
        console.print(Syntax(statement, "cedar", theme="monokai", line_numbers=False))
        console.print()

    # Show SDK invocation example
    console.rule("[bold cyan]Invoking Tools with Session Tracking[/]")
    show_invocation_example()
    console.print()

    # Show curl examples
    show_curl_examples()
    console.print()

    # Show important considerations
    console.rule("[bold cyan]Key Considerations[/]")
    console.print()
    console.print(
        "[bold]Session scoping:[/]\n"
        "  Temporal history is scoped to a session ID. A new session starts\n"
        "  with empty history. The caller supplies the session ID via the\n"
        "  x-amzn-bedrock-agentcore-policy-session-id header.\n\n"
        "[bold]Event recording:[/]\n"
        "  - Permitted actions are recorded as ::response events\n"
        "  - Denied actions are recorded as ::error events\n"
        "  - A temporal condition matching ::response only sees permitted actions\n\n"
        "[bold]eventResource: resource[/]\n"
        "  Every temporal predicate MUST include eventResource: resource\n"
        "  to scope the match to the current request's gateway.\n\n"
        "[bold]Policy invalidation:[/]\n"
        "  Updating temporal policies invalidates active sessions.\n"
        "  The next request on an invalidated session returns HTTP 409.\n"
        "  Start a new session after policy changes.\n\n"
        "[bold]Rate limit caveat:[/]\n"
        "  Session-based rate limits apply per session, not per caller.\n"
        "  A caller can reset counts by starting a new session.\n"
        "  Use this for cooperative behavior shaping, not hard security limits.\n\n"
        "[bold]Quotas:[/]\n"
        "  - Max 25 temporal policies per engine\n"
        "  - Max 3 temporal operators per policy\n"
        "  - Max 24-hour time window per condition\n"
    )


if __name__ == "__main__":
    main()
