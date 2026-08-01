"""Strands Agent that connects to MCP servers for customer service.

Uses MCPClient with both streamable HTTP (local customer-service MCP).

Run: python -m agent_mcp.agent_service
"""

import logging
import os
import warnings

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

from dotenv import load_dotenv
from mcp import stdio_client, StdioServerParameters
from mcp.client.streamable_http import streamablehttp_client
from rich.console import Console
from rich.markdown import Markdown
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


SYSTEM_PROMPT = """You are a customer service agent. You help users look up customer
information, check order history, and process refunds."""

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8000/mcp")

# Remote MCP server (Streamable HTTP) — customer service tools
customer_service_mcp = MCPClient(
    lambda: streamablehttp_client(MCP_SERVER_URL),
    prefix="customer"
)


def main() -> None:
    callback = RichCallbackHandler()

    agent = Agent(
        tools=[customer_service_mcp],
        system_prompt=SYSTEM_PROMPT,
        callback_handler=callback,
    )

    console.print("[bold]Customer Service Agent[/bold]")
    console.print("[dim]Tools: customer-service MCP")
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
