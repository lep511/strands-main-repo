"""Interactive multi-turn chat for Module 2: Hooks.

The notebook runs the agent one prompt at a time (each cell is one turn). This
script wraps the same agent - with the RateLimiterHook from the notebook - in a
loop so you can hold a real multi-turn conversation in the terminal. The rate
limiter resets at the start of each turn (each agent invocation).

From the cloned repo root:

    cd samples/02-hooks
    pip install -r requirements.txt
    python chat.py

Type 'quit', 'exit', or press Ctrl+C to stop.
"""

import logging
import time

from strands import Agent
from strands.models import BedrockModel
from strands.hooks import (
    HookProvider, HookRegistry,
    BeforeInvocationEvent, BeforeToolCallEvent, AfterToolCallEvent,
)

logger = logging.getLogger(__name__)
from customer_service_tools import lookup_customer, get_order_history, process_refund

class RateLimiterHook(HookProvider):
    """Caps each tool at max_calls per agent invocation."""

    def __init__(self, max_calls: int = 3):
        self.max_calls = max_calls
        self.counts: dict[str, int] = {}

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeInvocationEvent, self.reset)
        registry.add_callback(BeforeToolCallEvent, self.check)

    def reset(self, event: BeforeInvocationEvent) -> None:
        """Reset counts at the start of each invocation."""
        self.counts = {}
        print("[HOOK] 🔄 Rate limiter reset")

    def check(self, event: BeforeToolCallEvent) -> None:
        """Check and enforce the rate limit before each tool call."""
        name = event.tool_use["name"]
        current = self.counts.get(name, 0)

        if current >= self.max_calls:
            event.cancel_tool = (
                f"'{name}' hit the {self.max_calls}-call limit. "
                "Do NOT call this tool again."
            )
            print(f"[HOOK] 🚫 BLOCKED: {name} exceeded limit!")
            return

        self.counts[name] = current + 1
        print(f"[HOOK] 📊 {name}: call {self.counts[name]}/{self.max_calls}")


class ToolRetryHook(HookProvider):
    """Retries failed tool calls up to max_retries times per tool_use_id."""

    def __init__(self, max_retries: int = 3, backoff_secs: float = 2.0):
        self.max_retries = max_retries
        self.backoff_secs = backoff_secs
        self._attempt_counts: dict[str, int] = {}

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(AfterToolCallEvent, self.handle_retry)

    def handle_retry(self, event: AfterToolCallEvent) -> None:
        tool_use_id = str(event.tool_use.get("toolUseId", ""))
        tool_name = event.tool_use.get("name", "unknown")

        attempt = self._attempt_counts.get(tool_use_id, 0) + 1
        self._attempt_counts[tool_use_id] = attempt

        if event.result.get("status") == "error" and attempt <= self.max_retries:
            print(
                f"[HOOK] ⚠️ Tool '{tool_name}' failed. "
                f"Retrying attempt {attempt}/{self.max_retries}..."
            )
            time.sleep(self.backoff_secs)
            event.retry = True
        elif event.result.get("status") != "error":
            self._attempt_counts.pop(tool_use_id, None)


SYSTEM_PROMPT = """You are a customer service agent for an online electronics store.
Be helpful, professional, and concise. Use the available tools to look up customer
information and process requests."""


def main():
    # One agent instance reused across turns keeps conversation history in
    # agent.messages, which is what makes the conversation multi-turn.
    agent = Agent(
        tools=[lookup_customer, get_order_history, process_refund],
        hooks=[RateLimiterHook(max_calls=3), ToolRetryHook(max_retries=3)],
        system_prompt=SYSTEM_PROMPT,
    )

    print("Customer service agent (rate-limited) - type 'quit' to exit.")
    print("Try: \"Hi, I'm customer C-1001. What are my recent orders?\"\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in {"quit", "exit", "q"}:
            print("Goodbye!")
            break
        if not user_input:
            continue

        print("\nAgent: ", end="")
        agent(user_input)
        print()


if __name__ == "__main__":
    main()
