"""Weather agent that communicates exclusively via MCP with the Lambda MicroVM."""

import atexit
import logging
import os
import time
import warnings

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

os.environ["OTEL_SDK_DISABLED"] = "true"

from datetime import datetime
from pathlib import Path

import boto3
import httpx
from mcp.client.streamable_http import streamablehttp_client
from rich.console import Console
from rich.markdown import Markdown
from strands import Agent, tool
from strands.tools.mcp import MCPClient

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
                    f"{k}={v}" for k, v in tool_input.items()
                    if k not in ("current", "daily", "hourly")
                )
                if details:
                    self.status.update(f"[bold cyan]Calling [yellow]{name}[/yellow]({details})")


SYSTEM_PROMPT = """You are a helpful weather assistant. You have access to MCP tools running
on a Lambda MicroVM that connect to the Open-Meteo API.

Available MCP tools:
- get_weather: Get current conditions and daily forecast for a location
- get_hourly_forecast: Get hour-by-hour forecast for a location

When a user asks about the weather:
1. Use the appropriate MCP tool to fetch the data
2. Present the information using markdown formatting (headers, bold, tables)
3. Use markdown tables for daily/hourly forecasts
4. Include relevant details like temperature, wind, humidity, and conditions

You can handle questions like:
- "What's the weather in Tokyo?"
- "Will it rain in London tomorrow?"
- "Compare the weather in New York and Paris"
- "What's the hourly forecast for Berlin?"
- "What's the forecast for the next 5 days in Sydney?"

If the user provides a city name, use your knowledge to determine the approximate
latitude and longitude. Always use celsius unless the user asks for fahrenheit.

You can also save weather reports using the save_report tool. When the user asks
to save a report, include the weather data in markdown format with source attribution.

Format your responses using markdown. Use tables like:
| Date | Condition | High | Low | Precipitation |
|------|-----------|------|-----|---------------|
"""

REGION = os.environ.get("AWS_REGION", "us-east-1")
IMAGE_NAME = os.environ.get("MICROVM_IMAGE_NAME", "microvm-rust-app")

microvm_client = boto3.client("lambda-microvms", region_name=REGION)
sts_client = boto3.client("sts", region_name=REGION)

microvm_state = {"id": None, "endpoint": None}


def get_account_id() -> str:
    return sts_client.get_caller_identity()["Account"]


def start_microvm() -> tuple[str, str]:
    """Run a new MicroVM and return (microvm_id, endpoint)."""
    account_id = get_account_id()
    image_arn = f"arn:aws:lambda:{REGION}:{account_id}:microvm-image:{IMAGE_NAME}"
    execution_role = f"arn:aws:iam::{account_id}:role/MicroVMExecutionRole"

    image_info = microvm_client.get_microvm_image(imageIdentifier=image_arn)
    image_version = image_info.get("latestActiveImageVersion", "1.0")

    response = microvm_client.run_microvm(
        imageIdentifier=image_arn,
        imageVersion=image_version,
        executionRoleArn=execution_role,
        idlePolicy={
            "maxIdleDurationSeconds": 900,
            "suspendedDurationSeconds": 300,
            "autoResumeEnabled": True,
        },
    )

    microvm_id = response["microvmId"]
    endpoint = response["endpoint"]
    return microvm_id, endpoint


def get_auth_token(microvm_id: str, port: int = 8080) -> str:
    """Mint a fresh auth token for a specific MicroVM port."""
    response = microvm_client.create_microvm_auth_token(
        microvmIdentifier=microvm_id,
        expirationInMinutes=30,
        allowedPorts=[{"port": port}],
    )
    return response["authToken"]["X-aws-proxy-auth"]


def wait_for_microvm_ready(endpoint: str, microvm_id: str, timeout: int = 60):
    """Poll the MicroVM until the health endpoint responds."""
    elapsed = 0
    while elapsed < timeout:
        try:
            token = get_auth_token(microvm_id, port=8080)
            resp = httpx.get(
                f"https://{endpoint}/health",
                headers={"X-aws-proxy-auth": token, "X-aws-proxy-port": "8080"},
                timeout=5,
            )
            if resp.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(2)
        elapsed += 2
    raise TimeoutError(f"MicroVM did not become ready within {timeout}s")


def terminate_microvm():
    """Terminate the running MicroVM (registered with atexit)."""
    if microvm_state["id"]:
        try:
            microvm_client.terminate_microvm(microvmIdentifier=microvm_state["id"])
            console.print(f"\n[dim]MicroVM {microvm_state['id']} terminated.[/dim]")
        except Exception:
            pass
        microvm_state["id"] = None


REPORTS_DIR = Path("reports")


@tool
def save_report(title: str, content: str) -> str:
    """Save a weather report to disk as a markdown file.

    Args:
        title: The report title (used as filename, e.g., 'tokyo-weather-2026-07-21')
        content: The full markdown content of the weather report including source data
    """
    REPORTS_DIR.mkdir(exist_ok=True)
    filename = f"{title}.md"
    path = REPORTS_DIR / filename
    header = f"# {title}\n\n_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n\n"
    path.write_text(header + content)
    return f"Report saved to {path}"


def main():
    atexit.register(terminate_microvm)
    callback = RichCallbackHandler()

    console.print("[bold]Weather Agent (MCP Only) - Interactive Chat[/bold]")
    console.print()

    try:
        with console.status("[bold cyan]Starting MicroVM..."):
            microvm_id, endpoint = start_microvm()
            microvm_state["id"] = microvm_id
            microvm_state["endpoint"] = endpoint
    except boto3.exceptions.Boto3Error as e:
        console.print(f"[bold red]Error:[/bold red] Failed to start MicroVM: {e}")
        console.print("[dim]Check your AWS credentials and that the MicroVM image exists.[/dim]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] Failed to start MicroVM: {e}")
        raise SystemExit(1)

    console.print(f"  MicroVM started: [cyan]{microvm_id}[/cyan]")
    console.print(f"  Endpoint: [cyan]{endpoint}[/cyan]")

    try:
        with console.status("[bold cyan]Waiting for MicroVM to be ready..."):
            wait_for_microvm_ready(endpoint, microvm_id)
    except TimeoutError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        console.print("[dim]The MicroVM started but the health check never passed.[/dim]")
        raise SystemExit(1)

    console.print("  [green]MicroVM is ready![/green]")
    console.print()

    try:
        mcp_token = get_auth_token(microvm_id, port=8081)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] Failed to create MCP auth token: {e}")
        raise SystemExit(1)

    mcp_url = f"https://{endpoint}/mcp"
    mcp_headers = {"X-aws-proxy-auth": mcp_token, "X-aws-proxy-port": "8081"}

    mcp_client = MCPClient(
        lambda: streamablehttp_client(url=mcp_url, headers=mcp_headers)
    )

    try:
        agent = Agent(
            system_prompt=SYSTEM_PROMPT,
            tools=[mcp_client, save_report],
            callback_handler=callback,
        )
    except Exception as e:
        msg = str(e)
        if "403" in msg or "Forbidden" in msg:
            console.print("[bold red]Error:[/bold red] MCP connection rejected (403 Forbidden).")
            console.print("[dim]The auth token may not have access to port 8081, or it expired.[/dim]")
        elif "InitializationError" in type(e).__name__ or "connection" in msg.lower():
            console.print(f"[bold red]Error:[/bold red] Could not connect to MCP server at {mcp_url}")
            console.print("[dim]Verify the MicroVM is running and port 8081 is serving MCP.[/dim]")
        else:
            console.print(f"[bold red]Error:[/bold red] Failed to initialize agent: {e}")
        raise SystemExit(1)

    console.print("  [green]MCP client configured (managed lifecycle)[/green]")
    console.print()
    console.print("Ask me about the weather anywhere in the world!")
    console.print("Type 'quit' or 'exit' to end the conversation.")
    console.print("-" * 50)

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            console.print("Goodbye!")
            break

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
            elif "403" in msg or "token" in msg.lower():
                console.print("[bold yellow]Auth token may have expired.[/bold yellow] Restarting MCP connection...")
                try:
                    mcp_token = get_auth_token(microvm_id, port=8081)
                    mcp_headers["X-aws-proxy-auth"] = mcp_token
                    mcp_client_new = MCPClient(
                        lambda: streamablehttp_client(url=mcp_url, headers=mcp_headers)
                    )
                    agent = Agent(
                        system_prompt=SYSTEM_PROMPT,
                        tools=[mcp_client_new, save_report],
                        callback_handler=callback,
                    )
                    console.print("[green]Reconnected.[/green] Please try your question again.")
                except Exception as reconnect_err:
                    console.print(f"[bold red]Reconnection failed:[/bold red] {reconnect_err}")
            else:
                console.print(f"[bold red]Error:[/bold red] {e}")
            continue


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\nGoodbye!")
    except SystemExit:
        pass
