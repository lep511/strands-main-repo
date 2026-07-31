"""Process Refund Cedar policy example.

Demonstrates authorization for refund processing where:
- Refunds under $500 are automatically permitted
- Refunds for orders older than 90 days are forbidden (regardless of amount)
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime as dt
from datetime import timezone
from typing import Any

import cedarpy
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from strands import Agent, tool
from strands.hooks.events import BeforeToolCallEvent
from strands.interventions.actions import Deny, Proceed
from strands.interventions.handler import InterventionHandler, OnError
from strands.vended_interventions.cedar._file_loaders import load_policies

console = Console()

TypeAndId = dict[str, str]
PrincipalResolver = Callable[[dict[str, Any]], TypeAndId | None]

_POLICIES = load_policies("./policies/process_refund_policy/process_refund_policy.cedar")

_ENTITIES = [
    {
        "uid": {"type": "AgentCore::User", "id": "agent_support_01"},
        "attrs": {},
        "parents": [],
    },
    {
        "uid": {"type": "AgentCore::Resource", "id": "refund_system"},
        "attrs": {},
        "parents": [],
    },
]


class RefundCedarAuthorization(InterventionHandler):
    """Cedar authorization handler for refund processing."""

    name = "cedar-refund-authorization"

    @property
    def on_error(self) -> OnError:
        return self._on_error

    def __init__(
        self,
        *,
        policies: str,
        entities: list[dict[str, Any]],
        principal_resolver: PrincipalResolver,
        on_error: OnError = "throw",
    ) -> None:
        self._on_error = on_error
        self._policies = policies
        self._entities = entities
        self._principal_resolver = principal_resolver

    def before_tool_call(self, event: BeforeToolCallEvent, **kwargs: Any) -> Proceed | Deny:
        invocation_state = event.invocation_state

        try:
            principal = self._principal_resolver(invocation_state)
        except Exception as e:
            if self._on_error == "proceed":
                return Proceed(reason=f"principal_resolver failed but on_error='proceed': {e}")
            if self._on_error == "deny":
                return Deny(reason=f"principal_resolver failed: {e}")
            raise

        if not principal or not principal.get("type") or not principal.get("id"):
            return Deny(reason="No principal identity found in invocation state")

        tool_name = event.tool_use["name"]
        tool_input = event.tool_use.get("input") or {}

        now_iso = dt.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        order_date = tool_input.get("order_date", now_iso)

        request = {
            "principal": f'AgentCore::User::"{principal["id"]}"',
            "action": f'AgentCore::Action::"{tool_name}"',
            "resource": 'AgentCore::Resource::"refund_system"',
            "context": {
                "input": {
                    "refundAmount": tool_input.get("refund_amount", 0),
                    "orderDate": {"__extn": {"fn": "datetime", "arg": order_date}},
                },
                "system": {
                    "now": {"__extn": {"fn": "datetime", "arg": now_iso}},
                },
            },
        }

        try:
            result = cedarpy.is_authorized(request, self._policies, self._entities)
        except Exception as e:
            # Cedar engine failures are always fail-closed regardless of on_error
            return Deny(reason=f"Cedar engine error (always denied): {e}")

        if not result.allowed:
            refund_amount = tool_input.get("refund_amount", 0)
            reasons = []
            if refund_amount >= 500:
                reasons.append(f"Refund amount ${refund_amount} exceeds the $500 limit.")
            if order_date != now_iso:
                from datetime import timedelta
                order_dt = dt.fromisoformat(order_date.replace("Z", "+00:00"))
                now_dt = dt.now(timezone.utc)
                if (now_dt - order_dt).days > 90:
                    days_since = (now_dt - order_dt).days
                    reasons.append(f"Order is {days_since} days old, exceeding the 90-day refund window.")
            if not reasons:
                reasons.append("Policy conditions not met.")
            return Deny(
                reason=f"Access denied for action '{tool_name}'. {' '.join(reasons)}"
            )

        return Proceed()


@tool
def ProcessRefund(order_id: str, refund_amount: int, order_date: str) -> str:
    """Process a refund for a given order. order_date must be in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)."""
    return f"Refund of ${refund_amount} processed for order {order_id} (ordered on {order_date})"


cedar = RefundCedarAuthorization(
    policies=_POLICIES,
    entities=_ENTITIES,
    principal_resolver=lambda state: (
        {"type": "User", "id": state["agent_id"]}
        if state.get("agent_id")
        else None
    ),
)

ALL_TOOLS = [ProcessRefund]


def run_scenario(title: str, style: str, prompt: str, invocation_state: dict):
    console.rule(f"[bold {style}]{title}[/]")
    agent = Agent(
        tools=ALL_TOOLS,
        interventions=[cedar],
        callback_handler=lambda **kwargs: None,
    )
    result = agent(prompt, invocation_state=invocation_state)
    console.print(Panel(Markdown(str(result)), border_style=style))
    console.print()


if __name__ == "__main__":
    console.print(Panel(
        "[bold]Cedar Process Refund Policy[/]\n"
        "Policy: policies/process_refund_policy/process_refund_policy.cedar\n\n"
        "Rules:\n"
        "  - Refunds under $500 are permitted\n"
        "  - Refunds for orders older than 90 days are forbidden\n"
        "  - Both rules are evaluated: a $200 refund on a 100-day order is DENIED",
        title="Demo",
    ))
    console.print()

    # Scenario 1: Small refund, recent order - PERMITTED
    run_scenario(
        title="Agent: $150 refund, order from 10 days ago - PERMITTED",
        style="green",
        prompt="Process a refund of $150 for order ORD-1001 placed on 2026-07-21T10:00:00Z",
        invocation_state={"agent_id": "agent_support_01"},
    )

    # Scenario 2: Small refund, old order (>90 days) - DENIED
    run_scenario(
        title="Agent: $100 refund, order from 120 days ago - DENIED (too old)",
        style="red",
        prompt="Process a refund of $100 for order ORD-1002 placed on 2026-04-01T10:00:00Z",
        invocation_state={"agent_id": "agent_support_01"},
    )

    # Scenario 3: Large refund (>=$500), recent order - DENIED
    run_scenario(
        title="Agent: $750 refund, recent order - DENIED (amount too high)",
        style="red",
        prompt="Process a refund of $750 for order ORD-1003 placed on 2026-07-25T10:00:00Z",
        invocation_state={"agent_id": "agent_support_01"},
    )

    # Scenario 4: Exactly $499 refund, recent order - PERMITTED
    run_scenario(
        title="Agent: $499 refund, recent order - PERMITTED (just under limit)",
        style="green",
        prompt="Process a refund of $499 for order ORD-1004 placed on 2026-07-20T10:00:00Z",
        invocation_state={"agent_id": "agent_support_01"},
    )
