"""Interactive weather chat agent using Strands Agents and the MicroVM weather endpoint."""

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
from rich.console import Console
from rich.markdown import Markdown
from strands import Agent, tool
from strands.hooks import BeforeToolCallEvent

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

SYSTEM_PROMPT = """You are a helpful weather assistant. You can look up current weather
conditions and forecasts for any location in the world using your weather tool,
which connects to a Lambda MicroVM running a Rust server with the Open-Meteo API.

When a user asks about the weather:
1. Use the get_weather tool to fetch the data
2. Present the information using markdown formatting (headers, bold, tables)
3. Use markdown tables for daily forecasts
4. Include relevant details like temperature, wind, humidity, and conditions

You can handle questions like:
- "What's the weather in Tokyo?"
- "Will it rain in London tomorrow?"
- "Compare the weather in New York and Paris"
- "What's the forecast for the next 3 days in Berlin?"

If the user provides a city name, use your knowledge to determine the approximate
latitude and longitude. Always use celsius unless the user asks for fahrenheit.

You can also save weather reports using the save_report tool. When the user asks
to save a report, include the weather data in markdown format with source attribution
(e.g., "Source: Open-Meteo via Lambda MicroVM"). Reports are saved to the reports/ directory.

Format your responses using markdown. Use tables like:
| Date | Condition | High | Low | Precipitation |
|------|-----------|------|-----|---------------|
"""

WMO_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


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


def wait_for_microvm_ready(endpoint: str, microvm_id: str, timeout: int = 60):
    """Poll the MicroVM until it responds to health checks."""
    elapsed = 0
    while elapsed < timeout:
        try:
            token = get_auth_token(microvm_id)
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


def get_auth_token(microvm_id: str) -> str:
    """Mint a fresh auth token for the MicroVM using boto3."""
    response = microvm_client.create_microvm_auth_token(
        microvmIdentifier=microvm_id,
        expirationInMinutes=30,
        allowedPorts=[{"port": 8080}],
    )
    return response["authToken"]["X-aws-proxy-auth"]


@tool
def get_weather(
    latitude: float,
    longitude: float,
    current: str = "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,wind_direction_10m,weather_code",
    daily: str = "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
    timezone: str = "auto",
    forecast_days: int = 3,
    temperature_unit: str = "celsius",
) -> str:
    """Fetch weather data from the MicroVM weather endpoint for a given location.

    Args:
        latitude: The latitude of the location (e.g., 52.52 for Berlin)
        longitude: The longitude of the location (e.g., 13.41 for Berlin)
        current: Comma-separated current weather variables to fetch
        daily: Comma-separated daily weather variables to fetch
        timezone: Timezone for the response (use 'auto' to detect from coordinates)
        forecast_days: Number of forecast days (1-16)
        temperature_unit: Temperature unit - 'celsius' or 'fahrenheit'
    """
    endpoint = microvm_state["endpoint"]
    microvm_id = microvm_state["id"]

    if not endpoint or not microvm_id:
        return "Error: MicroVM is not running."

    token = get_auth_token(microvm_id)

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": current,
        "daily": daily,
        "timezone": timezone,
        "forecast_days": forecast_days,
        "temperature_unit": temperature_unit,
    }

    try:
        response = httpx.get(
            f"https://{endpoint}/weather",
            params=params,
            headers={
                "X-aws-proxy-auth": token,
                "X-aws-proxy-port": "8080",
            },
            timeout=15,
        )
    except httpx.ConnectError:
        return "Error: Could not connect to the MicroVM. It may be suspended or terminated."
    except httpx.TimeoutException:
        return "Error: Request to the weather service timed out. The MicroVM may be resuming - please try again."

    if response.status_code == 403:
        return "Error: Auth token expired or invalid. Type 'refresh-token' to get a new one."
    if response.status_code != 200:
        return f"Error fetching weather data: {response.status_code} - {response.text}"

    data = response.json()

    result_parts = []
    result_parts.append(f"Location: {data['latitude']}N, {data['longitude']}E")
    result_parts.append(f"Timezone: {data.get('timezone', 'Unknown')}")
    result_parts.append(f"Elevation: {data.get('elevation', 'Unknown')}m")

    if "current" in data:
        current_data = data["current"]
        weather_code = current_data.get("weather_code", 0)
        condition = WMO_CODES.get(weather_code, f"Code {weather_code}")
        unit = "F" if temperature_unit == "fahrenheit" else "C"
        result_parts.append("\n--- Current Conditions ---")
        result_parts.append(f"Condition: {condition}")
        result_parts.append(f"Temperature: {current_data.get('temperature_2m')} {unit}")
        result_parts.append(f"Feels like: {current_data.get('apparent_temperature')} {unit}")
        result_parts.append(f"Humidity: {current_data.get('relative_humidity_2m')}%")
        result_parts.append(f"Wind: {current_data.get('wind_speed_10m')} km/h")
        result_parts.append(f"Wind direction: {current_data.get('wind_direction_10m')} degrees")

    if "daily" in data:
        daily_data = data["daily"]
        unit = "F" if temperature_unit == "fahrenheit" else "C"
        result_parts.append("\n--- Daily Forecast ---")
        for i, date in enumerate(daily_data.get("time", [])):
            weather_code = daily_data["weather_code"][i] if "weather_code" in daily_data else 0
            condition = WMO_CODES.get(weather_code, f"Code {weather_code}")
            high = daily_data.get("temperature_2m_max", [None])[i]
            low = daily_data.get("temperature_2m_min", [None])[i]
            precip = daily_data.get("precipitation_sum", [None])[i]
            result_parts.append(f"  {date}: {condition}, High: {high} {unit}, Low: {low} {unit}, Precipitation: {precip} mm")

    return "\n".join(result_parts)


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


def require_weather_source(event: BeforeToolCallEvent):
    """Ensure save_report includes weather source attribution."""
    if event.tool_use["name"] == "save_report":
        content = str(event.tool_use.get("input", {}).get("content", ""))
        if "open-meteo" not in content.lower() and "microvm" not in content.lower():
            event.cancel_tool = "Add source attribution (e.g., 'Source: Open-Meteo via Lambda MicroVM')."


def main():
    atexit.register(terminate_microvm)
    callback = RichCallbackHandler()

    console.print("[bold]Weather Agent - Interactive Chat[/bold]")
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

    agent = Agent(
        system_prompt=SYSTEM_PROMPT,
        tools=[get_weather, save_report],
        callback_handler=callback,
        hooks=[require_weather_source],
    )

    console.print("Ask me about the weather anywhere in the world!")
    console.print("You can also ask me to save a weather report.")
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
                console.print("[bold yellow]Auth token may have expired.[/bold yellow] Refreshing...")
                try:
                    token = get_auth_token(microvm_id)
                    console.print("[green]Token refreshed.[/green] Please try your question again.")
                except Exception as refresh_err:
                    console.print(f"[bold red]Token refresh failed:[/bold red] {refresh_err}")
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

