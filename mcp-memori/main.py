from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import logging
import os
import sys

import httpx2
from mcp.client.streamable_http import streamable_http_client
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from strands import Agent
from strands.tools.mcp import MCPClient

load_dotenv()

logging.getLogger("strands").setLevel(logging.CRITICAL)

console = Console()

MEMORI_URL = "https://api.memorilabs.ai/mcp/"
ENTITY_ID = "user_123"
PROCESS_ID = "my_agent"


def build_system_prompt() -> str:
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    return f"""You are a helpful assistant with persistent memory powered by Memori.
Current date: {today}

You have access to memory tools via MCP. Use them proactively:

## Storing memories
- When the user shares preferences, facts, or personal info → call memori_advanced_augmentation
  with user_message and assistant_response to persist it.

## Recalling memories (ALWAYS prioritize the latest data)
- Use memori_recall with dateStart="{week_ago}" to get recent memories first.
  If no results, retry without date filter to search all history.
- Use memori_recall_summary with dateStart="{week_ago}" for broad session context.
- Use memori_compaction after long conversations to get a structured resume.

## Available date filters for recall tools
- dateStart: ISO date string (e.g. "{week_ago}") — only return memories from this date onward
- dateEnd: ISO date string (e.g. "{today}") — only return memories up to this date
- Always pass dateStart when the user asks about recent activity or current state.

## source/signal pairs for memori_recall
Use these to filter by memory type:
- fact + verification — for stored facts
- decision + commit — for decisions made
- constraint + discovery — for constraints/rules
- instruction + discovery — for instructions
- insight + inference — for derived insights
- status + update — for status updates
- task + result — for task outcomes

Always respond in the same language the user writes in.
Keep responses concise and useful."""


def create_mcp_client() -> MCPClient:
    api_key = os.getenv("MEMORI_API_KEY")
    if not api_key:
        console.print("[bold red]Error:[/] MEMORI_API_KEY not found. Add it to .env")
        sys.exit(1)

    return MCPClient(
        lambda: streamable_http_client(
            url=MEMORI_URL,
            http_client=httpx2.AsyncClient(
                headers={
                    "X-Memori-API-Key": api_key,
                    "X-Memori-Entity-Id": ENTITY_ID,
                    "X-Memori-Process-Id": PROCESS_ID,
                }
            ),
        )
    )


def show_tools(mcp_client: MCPClient):
    console.print("[dim]Available memory tools:[/]")
    for tool in mcp_client.list_tools_sync():
        desc = tool.tool_spec.get("description", "")
        console.print(f"  [yellow]{tool.tool_name}[/] — {desc}")
    console.print()


def main():
    console.print(Panel.fit("[bold]Memori MCP + Strands Agent[/]", style="blue"))
    console.print()

    mcp_client = create_mcp_client()

    with mcp_client:
        show_tools(mcp_client)

        tools = mcp_client.list_tools_sync()
        agent = Agent(
            tools=tools,
            system_prompt=build_system_prompt(),
            callback_handler=None,
        )

        console.print("[dim]Type your message or 'exit' to quit.[/]\n")

        while True:
            user_input = console.input("[bold yellow]You:[/] ").strip()

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                break

            with console.status("[blue]Thinking...[/]"):
                result = agent(user_input)

            console.print(Panel(Markdown(str(result)), title="Agent", style="blue"))
            console.print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Bye![/]")
