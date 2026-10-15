"""Strands Agent that connects to the customer-service MCP server.

Strands >= 1.61 runs on the mcp 2.x SDK. ``MCPClient(url=...)`` opens a
streamable HTTP transport and negotiates the best mutual protocol: it probes
``server/discover`` first and adopts the sessionless 2026-07-28 protocol when
the server supports it, falling back to the legacy ``initialize`` handshake
otherwise.

Multi round-trip requests (SEP-2322): when a tool such as ``process_refund``
answers ``input_required``, Strands resolves the embedded elicitation through
``elicitation_callback`` and retries the call with the user's answer. The
callback below asks the person at the terminal, so no refund happens without
explicit consent.

Run: python -m agent_mcp.agent_service
"""

import logging
import os
import warnings

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

from dotenv import load_dotenv
from mcp.types import ElicitResult
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from strands import Agent
from strands.tools.mcp import MCPClient

load_dotenv()

console = Console()


class RichCallbackHandler:
    """Callback handler that updates a Rich status spinner with tool call info."""

    def __init__(self):
        self.status = None
        self.tool_count = 0

    def __call__(self, **kwargs):
        event = kwargs.get("event", {})
        tool_start = event.get("contentBlockStart", {}).get("start", {}).get("toolUse")

        if tool_start and self.status:
            self.tool_count += 1
            name = tool_start.get("name", "?")
            self.status.update(f"[bold cyan]Calling [yellow]{name}[/yellow]...")

        current_tool = kwargs.get("current_tool_use")
        if current_tool and self.status:
            tool_input = current_tool.get("input", {})
            name = current_tool.get("name", "")
            if name and isinstance(tool_input, dict) and tool_input:
                details = ", ".join(
                    f"{k}={v}" for k, v in list(tool_input.items())[:4]
                )
                if details:
                    self.status.update(f"[bold cyan]Calling [yellow]{name}[/yellow]({details})")


callback = RichCallbackHandler()


def _parse_answer(raw: str, prop: dict):
    """Coerce a terminal answer to the JSON type the elicitation schema asks for."""
    kind = prop.get("type", "string")
    raw = raw.strip()
    if kind == "boolean":
        return raw.lower() in ("y", "yes", "true", "1", "ok")
    if kind == "integer":
        return int(raw)
    if kind == "number":
        return float(raw)
    return raw


async def ask_user_in_terminal(context, params) -> ElicitResult:
    """Elicitation callback: the server needs input from the user.

    Works for both protocol eras. On 2026-07-28 this is the client half of a
    multi round-trip request (the server returned ``input_required``); on a
    legacy connection it answers an ``elicitation/create`` back-channel call.
    """
    status = callback.status
    if status:
        status.stop()
    try:
        console.print()
        console.print(Panel(params.message, title="[bold]Server needs your input[/bold]", border_style="yellow"))

        schema = getattr(params, "requested_schema", None) or {}
        props = schema.get("properties", {})
        if not props:
            answer = console.input("[bold]Accept?[/bold] (y/n): ")
            if answer.strip().lower() in ("y", "yes"):
                return ElicitResult(action="accept", content={})
            return ElicitResult(action="decline")

        content = {}
        for key, prop in props.items():
            label = prop.get("title") or key
            hint = "(y/n)" if prop.get("type") == "boolean" else ""
            desc = prop.get("description")
            if desc:
                console.print(f"[dim]{desc}[/dim]")
            raw = console.input(f"[bold]{label}[/bold] {hint}: ")
            if not raw.strip():
                return ElicitResult(action="cancel")
            content[key] = _parse_answer(raw, prop)
        return ElicitResult(action="accept", content=content)
    except (EOFError, KeyboardInterrupt):
        return ElicitResult(action="cancel")
    finally:
        if status:
            status.start()


SYSTEM_PROMPT = """You are a customer service agent. You help users look up customer
information, check order history, and process refunds. Before calling process_refund,
tell the user what you are about to do; the tool itself will ask them to confirm."""

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8000/mcp")

# Streamable HTTP transport (mcp 2.x). Protocol negotiation is automatic:
# server/discover → 2026-07-28, else legacy initialize handshake.
customer_service_mcp = MCPClient(
    url=MCP_SERVER_URL,
    prefix="customer",
    application_name="agent-mcp-cli",
    elicitation_callback=ask_user_in_terminal,
)


def main() -> None:
    agent = Agent(
        tools=[customer_service_mcp],
        system_prompt=SYSTEM_PROMPT,
        callback_handler=callback,
    )

    console.print("[bold]Customer Service Agent[/bold]")
    console.print(f"[dim]MCP server: {MCP_SERVER_URL}")
    console.print("Type 'quit' to exit.")
    console.print("-" * 50)

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nGoodbye!")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            console.print("Goodbye!")
            break
        if not user_input:
            continue

        try:
            with console.status("[bold cyan]Thinking...") as status:
                callback.status = status
                result = agent(user_input)
                callback.status = None
            console.print()
            console.print(Markdown(str(result)))
        except KeyboardInterrupt:
            callback.status = None
            console.print("\n[dim]Interrupted.[/dim]")
            continue
        except Exception as e:
            callback.status = None
            msg = str(e)
            if "throttl" in msg.lower():
                console.print("[bold yellow]Rate limited.[/bold yellow] Please wait a moment and try again.")
            else:
                console.print(f"[bold red]Error:[/bold red] {msg}")
            continue


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\nGoodbye!")
    except SystemExit:
        pass
