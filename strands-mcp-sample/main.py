"""Test the MCP App server via a Strands Agent client.

Connects to the MCP App server on localhost:3001/mcp and exposes
the ask-agent tool for interactive use.

Run:
  uv run python main.py
"""

import logging
import warnings

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

from mcp.client.streamable_http import streamable_http_client
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from strands import Agent
from strands.tools.mcp import MCPClient

console = Console()

MCP_SERVER_URL = "http://localhost:3001/mcp"

mcp_client = MCPClient(lambda: streamable_http_client(MCP_SERVER_URL))

SYSTEM_PROMPT = (
    "You are a helpful assistant. Use the ask-agent tool to answer user questions. "
    "The tool connects to a Strands AI agent that can check weather and do calculations."
)


class RichCallbackHandler:
    def __init__(self):
        self.status = None

    def __call__(self, **kwargs):
        event = kwargs.get("event", {})
        tool_start = event.get("contentBlockStart", {}).get("start", {}).get("toolUse")
        if tool_start and self.status:
            self.status.update(f"[bold cyan]Calling [yellow]{tool_start.get('name', '?')}[/yellow]...")


def main() -> None:
    callback = RichCallbackHandler()

    agent = Agent(
        tools=[mcp_client],
        system_prompt=SYSTEM_PROMPT,
        callback_handler=callback,
    )

    console.print(Panel(
        "[bold]Strands MCP App Tester[/bold]\n"
        f"[dim]Connected to {MCP_SERVER_URL}[/dim]\n"
        "[dim]Type [bold]quit[/bold] to exit.[/dim]",
        border_style="cyan",
    ))

    while True:
        try:
            user_input = console.input("\n[bold blue]You>[/bold blue] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye![/dim]")
            break
        if not user_input:
            continue

        try:
            with console.status("[bold cyan]Thinking...") as status:
                callback.status = status
                result = agent(user_input)
                callback.status = None
            console.print()
            console.print(Panel(
                Markdown(str(result)),
                title="Agent Response",
                border_style="green",
            ))
        except KeyboardInterrupt:
            callback.status = None
            console.print("\n[dim]Interrupted.[/dim]")
        except Exception as e:
            callback.status = None
            console.print(f"[bold red]Error:[/bold red] {e}")


if __name__ == "__main__":
    main()
