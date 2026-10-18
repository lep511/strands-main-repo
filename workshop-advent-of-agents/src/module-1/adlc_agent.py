"""Day 1 prototype agent: weather + time, governed by DESIGN_SPEC.md.

Usage:
    uv run src/module-1/adlc_agent.py "What's the weather in San Francisco?"
    uv run src/module-1/adlc_agent.py --trace "What time is it in Tokyo?"
    uv run src/module-1/adlc_agent.py --rogue "Email the Tokyo weather to bob@example.com"
"""

import argparse
import os

from dotenv import load_dotenv
from strands import Agent, tool
from strands.models import BedrockModel

from adlc_tools import get_current_time, get_weather
from spec_guard import SpecGuard

load_dotenv()

MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-sonnet-4-6")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

SYSTEM_PROMPT = """You are the adlc-day1 assistant.
You answer questions about the current weather and the current local time in a city.
Always use get_weather for weather questions and get_current_time for time questions;
never guess. If a question is about anything else, say politely that it is out of scope."""

# Simulates prompt drift: someone edited the prompt (and added a tool) without
# updating DESIGN_SPEC.md. The model will try send_email; SpecGuard must stop it.
ROGUE_SYSTEM_PROMPT = """You are a helpful assistant. Use get_weather, get_current_time and
send_email whenever they help fulfil the request."""


@tool
def send_email(to: str, body: str) -> str:
    """Send an email. Exists only to demonstrate that SpecGuard blocks it.

    Args:
        to: Recipient address.
        body: Message body.
    """
    return f"Email sent to {to}"


def build_model() -> BedrockModel:
    return BedrockModel(model_id=MODEL_ID, region_name=AWS_REGION)


def build_agent(guard: SpecGuard | None = None, rogue: bool = False, **kwargs) -> Agent:
    tools = [get_weather, get_current_time]
    if rogue:
        tools.append(send_email)
    return Agent(
        name="adlc-day1",
        model=build_model(),
        system_prompt=ROGUE_SYSTEM_PROMPT if rogue else SYSTEM_PROMPT,
        tools=tools,
        hooks=[guard or SpecGuard()],
        **kwargs,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Day 1 ADLC agent")
    parser.add_argument("prompt", nargs="?", default="What's the weather in San Francisco?")
    parser.add_argument("--trace", action="store_true", help="print OpenTelemetry spans to the console")
    parser.add_argument("--rogue", action="store_true", help="drifted prompt + send_email tool, which the spec forbids")
    args = parser.parse_args()

    if args.trace:
        from strands.telemetry import StrandsTelemetry

        StrandsTelemetry().setup_console_exporter()

    agent = build_agent(rogue=args.rogue)
    result = agent(args.prompt)

    usage = result.metrics.accumulated_usage
    print(
        f"\n\n--- tools: {sorted(result.metrics.tool_metrics)} | "
        f"tokens in/out: {usage['inputTokens']}/{usage['outputTokens']} | "
        f"cycles: {result.metrics.cycle_count}"
    )


if __name__ == "__main__":
    main()
