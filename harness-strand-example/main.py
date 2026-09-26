import boto3
from botocore.exceptions import ClientError
from strands import Agent, tool
from strands.hooks import HookProvider, HookRegistry, MessageAddedEvent, AfterInvocationEvent
from strands.memory import MemoryManager
from strands.vended_memory_stores.test_memory_store import TestMemoryStore

from pathlib import Path
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live

REGION = "us-east-1"

console = Console()

MEMORY_PATH = str(Path.home() / ".strands" / "memory" / "rewards-agent.json")
store = TestMemoryStore(name="rewards-agent", path=MEMORY_PATH)

def list_guardrails():
    """List all Bedrock guardrails and their policy details."""
    client = boto3.client("bedrock", REGION)

    try:
        guardrails = []
        paginator = client.get_paginator("list_guardrails")
        for page in paginator.paginate():
            guardrails.extend(page.get("guardrails", []))
    except ClientError as e:
        console.print(Panel(
            f"Could not list guardrails: {e.response['Error']['Message']}",
            title="Guardrails Unavailable",
            border_style="yellow",
        ))
        return

    if not guardrails:
        console.print("[dim]No guardrails found.[/dim]\n")
        return

    table = Table(
        title="Bedrock Guardrails",
        title_style="bold cyan",
        border_style="cyan",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("ID", style="bold", no_wrap=True)
    table.add_column("Name", style="green")
    table.add_column("Status", no_wrap=True)
    table.add_column("Version", justify="center", no_wrap=True)
    table.add_column("Policies", ratio=2)

    for g in guardrails:
        gid = g["id"]
        status_color = "green" if g["status"] == "READY" else "yellow"

        policies = _get_policy_summary(client, gid, g["version"])

        table.add_row(
            gid,
            g.get("name", ""),
            f"[{status_color}]{g['status']}[/{status_color}]",
            g.get("version", "—"),
            policies,
        )

    console.print(table)
    console.print()


def _get_policy_summary(client, guardrail_id: str, version: str) -> Text:
    """Fetch guardrail detail and build a compact policy summary."""
    try:
        detail = client.get_guardrail(
            guardrailIdentifier=guardrail_id,
            guardrailVersion=version,
        )
    except ClientError:
        return Text("(details unavailable)", style="dim")

    summary = Text()

    topics = (detail.get("topicPolicy", {}).get("topics", []))
    if topics:
        summary.append("Topics: ", style="bold yellow")
        names = [f"{t['name']} ({t['type']})" for t in topics]
        summary.append(", ".join(names) + "\n", style="yellow")

    active_filters = [
        f for f in detail.get("contentPolicy", {}).get("filters", [])
        if f.get("inputStrength", "NONE") != "NONE" or f.get("outputStrength", "NONE") != "NONE"
    ]
    if active_filters:
        summary.append("Content: ", style="bold magenta")
        names = [f"{f['type']}={f.get('inputStrength', 'NONE')}" for f in active_filters]
        summary.append(", ".join(names) + "\n", style="magenta")

    pii = detail.get("sensitiveInformationPolicy", {}).get("piiEntities", [])
    if pii:
        summary.append("PII: ", style="bold blue")
        names = [f"{p['type']} → {p.get('inputAction', p.get('action', '?'))}" for p in pii]
        summary.append(", ".join(names), style="blue")

    return summary or Text("(no active policies)", style="dim")


# ---------------------------------------------------------------------------
# Strands custom tool — RewardsDatabase (DynamoDB)
# ---------------------------------------------------------------------------

dynamodb = boto3.resource("dynamodb", region_name=REGION)
rewards_table = dynamodb.Table("RewardsDatabase")
user_table = dynamodb.Table("UserTable")


@tool
def lookup_rewards_tier(tier: str) -> dict:
    """Look up a rewards tier in the RewardsDatabase to retrieve its details.

    Use this tool when the user asks about reward tiers, point limits, multipliers,
    or wants to compare tiers. Available tiers: plomo, bronze, silver, gold, platinum.

    Args:
        tier: The tier name to look up (e.g. "gold", "platinum"). Case-insensitive.

    Returns:
        A dict with tier, description, max_points, and multiplier_range,
        or an error message if the tier is not found.
    """
    try:
        response = rewards_table.get_item(Key={"tier": tier.lower().strip()})
        item = response.get("Item")
        if not item:
            return {"status": "error", "content": [{"text": f"Tier '{tier}' not found. Valid tiers: plomo, bronze, silver, gold, platinum."}]}
        return {
            "status": "success",
            "content": [{"json": {
                "tier": item["tier"],
                "description": item.get("description", ""),
                "max_points": int(item.get("max_points", 0)),
                "multiplier_range": item.get("multiplier_range", ""),
            }}],
        }
    except ClientError as e:
        return {"status": "error", "content": [{"text": f"DynamoDB error: {e.response['Error']['Message']}"}]}


@tool
def list_all_rewards_tiers() -> dict:
    """List every rewards tier available in the RewardsDatabase.

    Use this tool when the user wants to see all tiers, compare them side by side,
    or needs a summary of the full rewards program.

    Returns:
        A list of all tiers sorted by max_points ascending, each with
        tier name, description, max_points, and multiplier_range.
    """
    try:
        response = rewards_table.scan()
        items = response.get("Items", [])
        tiers = sorted(
            [
                {
                    "tier": item["tier"],
                    "description": item.get("description", ""),
                    "max_points": int(item.get("max_points", 0)),
                    "multiplier_range": item.get("multiplier_range", ""),
                }
                for item in items
            ],
            key=lambda t: t["max_points"],
        )
        return {"status": "success", "content": [{"json": {"tiers": tiers, "total": len(tiers)}}]}
    except ClientError as e:
        return {"status": "error", "content": [{"text": f"DynamoDB error: {e.response['Error']['Message']}"}]}


# ---------------------------------------------------------------------------
# Strands custom tool — UserTable (DynamoDB)
# ---------------------------------------------------------------------------

@tool
def register_user(name: str, email: str, phone: str, points: int) -> dict:
    """Register a new user in the UserTable with their contact info and points balance.

    Use this tool when the user wants to create or register a new account in the
    rewards program. All fields are required.

    Args:
        name: Full name of the user (e.g. "Maria Lopez").
        email: Email address (e.g. "maria@example.com").
        phone: Phone number (e.g. "+5491155551234").
        points: Initial points balance (must be >= 0).

    Returns:
        Confirmation with the created user data, or an error message.
    """
    email = email.strip().lower()
    if points < 0:
        return {"status": "error", "content": [{"text": "Points must be zero or positive."}]}
    try:
        user_table.put_item(
            Item={
                "PK": f"USER#{email}",
                "SK": "PROFILE",
                "name": name.strip(),
                "email": email,
                "phone": phone.strip(),
                "points": points,
            },
            ConditionExpression="attribute_not_exists(PK)",
        )
        return {
            "status": "success",
            "content": [{"json": {
                "message": "User registered successfully",
                "name": name.strip(),
                "email": email,
                "phone": phone.strip(),
                "points": points,
            }}],
        }
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return {"status": "error", "content": [{"text": f"A user with email '{email}' already exists."}]}
        return {"status": "error", "content": [{"text": f"DynamoDB error: {e.response['Error']['Message']}"}]}


@tool
def get_user(email: str) -> dict:
    """Look up a user by email in the UserTable.

    Use this tool when the user asks about their profile, points balance,
    or account details.

    Args:
        email: The email address of the user to look up.

    Returns:
        The user's name, email, phone, and points, or an error if not found.
    """
    email = email.strip().lower()
    try:
        response = user_table.get_item(Key={"PK": f"USER#{email}", "SK": "PROFILE"})
        item = response.get("Item")
        if not item:
            return {"status": "error", "content": [{"text": f"No user found with email '{email}'."}]}
        return {
            "status": "success",
            "content": [{"json": {
                "name": item.get("name", ""),
                "email": item.get("email", ""),
                "phone": item.get("phone", ""),
                "points": int(item.get("points", 0)),
            }}],
        }
    except ClientError as e:
        return {"status": "error", "content": [{"text": f"DynamoDB error: {e.response['Error']['Message']}"}]}


class RichCallbackHandler:
    """Streams agent output into a Rich Live display, rendered as Markdown."""

    def __init__(self):
        self.tool_count = 0
        self._buffer = ""
        self._live = Live(console=console, refresh_per_second=12, vertical_overflow="visible")

    def start(self):
        self._buffer = ""
        self._live.start()

    def stop(self):
        self._live.stop()

    def __call__(self, **kwargs):
        reasoning = kwargs.get("reasoningText", "")
        data = kwargs.get("data", "")
        complete = kwargs.get("complete", False)
        tool_use = kwargs.get("event", {}).get("contentBlockStart", {}).get("start", {}).get("toolUse")

        if reasoning:
            self._buffer += reasoning

        if data:
            self._buffer += data

        if tool_use:
            self.tool_count += 1
            tool_name = tool_use["name"]
            self._buffer += f"\n\n`🔧 Tool #{self.tool_count}: {tool_name}`\n\n"

        if self._buffer:
            self._live.update(Markdown(self._buffer))

        if complete:
            self._live.update(Markdown(self._buffer))


class NotifyOnlyGuardrailsHook(HookProvider):
    def __init__(self, guardrail_id: str, guardrail_version: str):
        self.guardrail_id = guardrail_id
        self.guardrail_version = guardrail_version
        self.bedrock_client = boto3.client("bedrock-runtime", REGION)

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(MessageAddedEvent, self.check_user_input)
        registry.add_callback(AfterInvocationEvent, self.check_assistant_response)

    def evaluate_content(self, content: str, source: str = "INPUT"):
        try:
            response = self.bedrock_client.apply_guardrail(
                guardrailIdentifier=self.guardrail_id,
                guardrailVersion=self.guardrail_version,
                source=source,
                content=[{"text": {"text": content}}],
            )

            if response.get("action") == "GUARDRAIL_INTERVENED":
                details = Text()
                details.append(f"Source: {source}\n", style="bold")
                details.append(f"Content: {content[:100]}...\n\n", style="dim")

                for assessment in response.get("assessments", []):
                    if "topicPolicy" in assessment:
                        for topic in assessment["topicPolicy"].get("topics", []):
                            details.append(f"  Topic Policy: ", style="yellow")
                            details.append(f"{topic['name']}", style="bold yellow")
                            details.append(f" → {topic['action']}\n", style="red")
                    if "contentPolicy" in assessment:
                        for f in assessment["contentPolicy"].get("filters", []):
                            details.append(f"  Content Policy: ", style="yellow")
                            details.append(f"{f['type']}", style="bold yellow")
                            details.append(f" → {f['confidence']} confidence\n", style="red")

                console.print(Panel(
                    details,
                    title="⚠ Guardrail Violation Detected",
                    title_align="left",
                    border_style="bold red",
                    padding=(1, 2),
                ))

        except Exception as e:
            console.print(Panel(
                f"Evaluation failed: {e}",
                title="⚠ Guardrail Error",
                title_align="left",
                border_style="bold yellow",
            ))

    def check_user_input(self, event: MessageAddedEvent) -> None:
        if event.message.get("role") == "user":
            content = "".join(block.get("text", "") for block in event.message.get("content", []))
            if content:
                self.evaluate_content(content, "INPUT")

    def check_assistant_response(self, event: AfterInvocationEvent) -> None:
        if event.agent.messages and event.agent.messages[-1].get("role") == "assistant":
            assistant_message = event.agent.messages[-1]
            content = "".join(block.get("text", "") for block in assistant_message.get("content", []))
            if content:
                self.evaluate_content(content, "OUTPUT")


callback = RichCallbackHandler()

agent = Agent(
    agent_id="rewards-assistant",
    system_prompt=(
        "You are a rewards program assistant. Use the available tools to look up "
        "tier details and list all tiers from the RewardsDatabase when users ask "
        "about rewards, points, multipliers, or tier benefits. "
        "Use add_memory to save important facts the user tells you (name, preferences, tier). "
        "Memory persists across sessions so you can recall past conversations."
    ),
    tools=[lookup_rewards_tier, list_all_rewards_tiers, register_user, get_user],
    hooks=[NotifyOnlyGuardrailsHook("9higgosxklzg", "DRAFT")],
    callback_handler=callback,
    memory_manager=MemoryManager(stores=[store], add_tool_config=True),
)

def main():
    console.print(
        Panel(
            "[bold]Strands Agent[/bold] with Bedrock Guardrails\n"
            "[dim]Type your message and press Enter. Type [bold]exit[/bold] or [bold]quit[/bold] to leave.[/dim]",
            border_style="cyan",
            padding=(0, 2),
        )
    )

    list_guardrails()

    while True:
        try:
            console.print()
            prompt = console.input("[bold blue]You>[/bold blue] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not prompt:
            continue
        if prompt.lower() in ("exit", "quit"):
            console.print("[dim]Goodbye![/dim]")
            break

        callback.start()
        try:
            result = agent(prompt)
        finally:
            callback.stop()

        console.print()
        console.print(Panel(
            Markdown(str(result)),
            title="Agent Response",
            title_align="left",
            border_style="green",
            padding=(1, 2),
        ))


if __name__ == "__main__":
    main()
