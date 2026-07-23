# Weather Chat Agent (Strands Agents + Lambda MicroVM)

An interactive chat agent built with [Strands Agents](https://strandsagents.com/) that answers weather questions using a Rust MicroVM backend. The agent automatically provisions a MicroVM on startup and terminates it on exit.

Two variants are provided:

| File | Communication | Description |
|------|--------------|-------------|
| `app_rest.py` | REST API | Agent uses a local `@tool` that calls the MicroVM `/weather` HTTP endpoint |
| `app_mcp.py` | MCP (Model Context Protocol) | Agent connects directly to the MicroVM MCP server on port 8081 |

## Architecture

**REST variant (`app_rest.py`)**
```
User <-> Strands Agent (Claude on Bedrock) <-> get_weather tool <-> Lambda MicroVM :8080/weather <-> Open-Meteo API
```

**MCP variant (`app_mcp.py`)**
```
User <-> Strands Agent (Claude on Bedrock) <-> MCP Client <-> Lambda MicroVM :8081/mcp <-> Open-Meteo API
```

The REST variant defines a local `get_weather` Python tool that makes HTTP calls to the MicroVM. The MCP variant discovers tools dynamically from the MicroVM MCP server - no local tool definitions needed for weather data.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) installed
- AWS credentials configured (for Bedrock model access and MicroVM operations)
- A deployed MicroVM image (`microvm-rust-app`) - see parent project's `deploy.sh`

## Quick Start

**REST variant** (local tool calls the MicroVM HTTP endpoint):
```bash
uv run app_rest.py
```

**MCP variant** (agent talks directly to MicroVM MCP server):
```bash
uv run app_mcp.py
```

Both will:
1. Create a new MicroVM instance automatically
2. Wait for it to be ready
3. Start the interactive chat
4. Terminate the MicroVM when you exit

## Usage

```
Weather Agent - Interactive Chat

  MicroVM started: microvm-69eaebfa-85bf-3f18-961f-d5d86c60ef4c
  Endpoint: aacfc2fa-049e-966d-c22a-233d7a297337.lambda-microvm.us-east-1.on.aws
  MicroVM is ready!

Ask me about the weather anywhere in the world!
You can also ask me to save a weather report.
Type 'quit' or 'exit' to end the conversation.
--------------------------------------------------

You: What's the weather in Tokyo?

  (spinner) Calling get_weather(latitude=35.68, longitude=139.69, timezone=auto, forecast_days=3)

## Current Weather in Tokyo

| Metric | Value |
|--------|-------|
| Temperature | 31.2 C |
| Feels like | 34.8 C |
| Condition | Partly cloudy |
| Humidity | 68% |
| Wind | 12.4 km/h |

## 3-Day Forecast

| Date | Condition | High | Low | Precipitation |
|------|-----------|------|-----|---------------|
| 2026-07-21 | Slight rain showers | 33 C | 25 C | 2.1 mm |
| 2026-07-22 | Partly cloudy | 31 C | 24 C | 0.0 mm |
| 2026-07-23 | Clear sky | 32 C | 25 C | 0.0 mm |

You: Save a report for Tokyo

  (spinner) Calling save_report(title=tokyo-weather-2026-07-21)

Report saved to reports/tokyo-weather-2026-07-21.md

You: quit
Goodbye!

MicroVM microvm-69eaebfa-85bf-3f18-961f-d5d86c60ef4c terminated.
```

## How It Works

1. **Startup**: boto3 calls `run_microvm` to create a fresh MicroVM instance, then polls until the health endpoint responds
2. The user asks a weather question in natural language
3. Claude (via Amazon Bedrock) interprets the question and determines the coordinates
4. The agent calls `get_weather` with latitude/longitude parameters
5. The tool mints a fresh auth token via boto3 and calls the MicroVM's `/weather` endpoint
6. The MicroVM proxies the request to Open-Meteo and returns the data
7. The agent formats and presents the results as rendered markdown (tables, bold, headers)
8. **Exit**: `atexit` hook calls `terminate_microvm` to clean up the instance

## Features

- **Auto-provisioning**: MicroVM is created on startup, no manual setup needed
- **Auto-cleanup**: MicroVM is terminated on exit (quit, Ctrl+C, or any termination)
- **Rich output**: Markdown rendered with tables and formatting via `rich`
- **Save reports**: Ask the agent to save a weather report to `reports/` directory
- **Source attribution hook**: Reports are rejected if they don't include data source attribution
- **Spinner with tool info**: Shows which tool is being called and with what parameters

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region for MicroVM and Bedrock |
| `MICROVM_IMAGE_NAME` | `microvm-rust-app` | Name of the deployed MicroVM image |

## Project Structure

```
strands-agent-sample/
├── app_rest.py      # REST variant: local get_weather tool calls MicroVM HTTP endpoint
├── app_mcp.py       # MCP variant: agent connects to MicroVM MCP server directly
├── pyproject.toml   # Dependencies: strands-agents, mcp, httpx, rich, boto3
├── uv.lock          # Locked dependencies
├── reports/         # Generated weather reports (created on first save)
└── README.md
```

## Tools

| Tool | Available in | Description |
|------|-------------|-------------|
| `get_weather` | REST | Local Python tool that calls the MicroVM `/weather` HTTP endpoint |
| `get_weather` | MCP | Discovered from MicroVM MCP server (current conditions + daily forecast) |
| `get_hourly_forecast` | MCP | Discovered from MicroVM MCP server (hour-by-hour data) |
| `save_report` | Both | Saves a weather report as a markdown file to `reports/` directory |

## Hooks (REST variant only)

| Hook | Purpose |
|------|---------|
| `require_weather_source` | Cancels `save_report` if the content doesn't include source attribution, forcing the agent to retry with proper citation |
