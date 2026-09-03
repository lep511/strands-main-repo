"""Dogwood-Style Temporal Authorization with Strands Agents.

Combines Cedar point-in-time policies (via Strands CedarAuthorization) with a
custom temporal event history tracker to simulate Dogwood's temporal conditions.

This demonstrates how to build a stock trading agent where:
1. Cedar handles point-in-time checks (share limits, role checks)
2. A temporal InterventionHandler enforces sequence-dependent rules:
   - Sales require prior approval (formerly)
   - Transfers are rate-limited (count_within)
   - Dollar caps are enforced (sum_within)

Since Dogwood's Rust-based interpreter is not yet available as a Python package,
this example implements the temporal layer in Python while using real Cedar
policies for the point-in-time checks via cedarpy.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import cedarpy
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from strands import Agent, tool
from strands.hooks.events import AfterToolCallEvent, BeforeToolCallEvent
from strands.interventions.actions import Deny, Proceed
from strands.interventions.handler import InterventionHandler, OnError

console = Console()


# ---------------------------------------------------------------------------
# Temporal event store
# ---------------------------------------------------------------------------

@dataclass
class ToolEvent:
    timestamp: float
    action: str
    kind: str  # "request" or "response"
    data: dict[str, Any] = field(default_factory=dict)


class TemporalStore:
    """In-memory event history for temporal policy evaluation."""

    def __init__(self):
        self.events: list[ToolEvent] = []

    def record(self, event: ToolEvent):
        self.events.append(event)

    def _window(self, now: float, seconds: float) -> list[ToolEvent]:
        cutoff = now - seconds
        return [e for e in self.events if e.timestamp >= cutoff]

    def formerly(
        self, now: float, window_s: float, action: str, kind: str, matcher: dict
    ) -> bool:
        for e in self._window(now, window_s):
            if e.action == action and e.kind == kind and self._match(e.data, matcher):
                return True
        return False

    def count_within(
        self, now: float, window_s: float, action: str, kind: str
    ) -> int:
        return sum(
            1 for e in self._window(now, window_s)
            if e.action == action and e.kind == kind
        )

    def sum_within(
        self, field: str, now: float, window_s: float, action: str, kind: str
    ) -> float:
        return sum(
            e.data.get(field, 0) for e in self._window(now, window_s)
            if e.action == action and e.kind == kind
        )

    @staticmethod
    def _match(data: dict, matcher: dict) -> bool:
        for k, v in matcher.items():
            if v == "_":
                continue
            if data.get(k) != v:
                return False
        return True


# ---------------------------------------------------------------------------
# Temporal intervention handler
# ---------------------------------------------------------------------------

WINDOW_1H = 3600.0

_store = TemporalStore()


class DogwoodTemporalAuthorization(InterventionHandler):
    """Enforces Dogwood-style temporal policies on Strands agent tool calls.

    This handler sits alongside Cedar's point-in-time policies and adds
    history-dependent checks that Cedar alone cannot express.
    """

    name = "dogwood-temporal-authorization"

    @property
    def on_error(self) -> OnError:
        return "deny"

    def before_tool_call(self, event: BeforeToolCallEvent, **kwargs: Any) -> Proceed | Deny:
        tool_name = event.tool_use["name"]
        tool_input = event.tool_use.get("input") or {}
        now = time.time()

        # Record the request event
        _store.record(ToolEvent(now, tool_name, "request", dict(tool_input)))

        # --- formerly: SellShares requires prior ApproveSale ---
        if tool_name == "SellShares":
            approved = _store.formerly(
                now, WINDOW_1H,
                action="ApproveSale", kind="response",
                matcher={
                    "stock": tool_input.get("stock"),
                    "shares": tool_input.get("shares"),
                    "approved": True,
                },
            )
            if not approved:
                return Deny(
                    reason=(
                        f"Dogwood temporal policy: SellShares requires a matching "
                        f"ApproveSale response within the last hour. "
                        f"No approval found for {tool_input.get('stock')} "
                        f"x{tool_input.get('shares')} shares."
                    )
                )

        # --- count_within: max 5 Transfer requests per hour ---
        if tool_name == "Transfer":
            count = _store.count_within(now, WINDOW_1H, "Transfer", "request")
            if count > 5:
                return Deny(
                    reason=(
                        f"Dogwood temporal policy: Transfer rate limit exceeded. "
                        f"{count} transfers in the last hour (max 5)."
                    )
                )

        # --- sum_within: max $5,000 in Transfer requests per hour ---
        if tool_name == "Transfer":
            total = _store.sum_within("amount", now, WINDOW_1H, "Transfer", "request")
            if total > 5000:
                return Deny(
                    reason=(
                        f"Dogwood temporal policy: Transfer dollar cap exceeded. "
                        f"${total:.0f} total in the last hour (max $5,000)."
                    )
                )

        return Proceed()

    def after_tool_call(self, event: AfterToolCallEvent, **kwargs: Any) -> Proceed:
        tool_name = event.tool_use["name"]
        tool_input = event.tool_use.get("input") or {}
        now = time.time()

        response_data = dict(tool_input)
        if tool_name == "ApproveSale":
            import json
            try:
                result_text = str(event.tool_result.get("content", [{}])[0].get("text", ""))
                result_obj = json.loads(result_text)
                response_data["approved"] = result_obj.get("approved", False)
            except (json.JSONDecodeError, IndexError, AttributeError, TypeError):
                response_data["approved"] = True

        _store.record(ToolEvent(now, tool_name, "response", response_data))
        return Proceed()


# ---------------------------------------------------------------------------
# Tools: Stock trading agent
# ---------------------------------------------------------------------------

@tool
def ApproveSale(stock: str, shares: int) -> str:
    """Request approval to sell shares of a stock. Returns approval status."""
    return f'{{"stock": "{stock}", "shares": {shares}, "approved": true}}'


@tool
def SellShares(stock: str, shares: int) -> str:
    """Sell a given number of shares of a stock. Requires prior approval."""
    return f"Sold {shares} shares of {stock}"


@tool
def Transfer(user: str, amount: int) -> str:
    """Transfer money to a user."""
    return f"Transferred ${amount} to {user}"


@tool
def GetStockInfo(stock: str) -> str:
    """Get current stock information."""
    return f'{{"stock": "{stock}", "price": 185.50, "change": "+2.3%"}}'


# ---------------------------------------------------------------------------
# Cedar point-in-time policies (non-temporal checks)
# ---------------------------------------------------------------------------

from strands.vended_interventions.cedar import CedarAuthorization

cedar = CedarAuthorization(
    policies="""
      // Anyone can get stock info
      permit(principal, action == Action::"GetStockInfo", resource);

      // Anyone can request approval
      permit(principal, action == Action::"ApproveSale", resource);

      // SellShares permitted (temporal check handled by DogwoodTemporalAuthorization)
      permit(principal, action == Action::"SellShares", resource)
      when { context.input.shares <= 1000 };

      // Transfers permitted (temporal checks handled separately)
      permit(principal, action == Action::"Transfer", resource);
    """,
)

temporal = DogwoodTemporalAuthorization()


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

ALL_TOOLS = [ApproveSale, SellShares, Transfer, GetStockInfo]


def run_scenario(title: str, style: str, prompt: str, tools: list | None = None):
    console.rule(f"[bold {style}]{title}[/]")
    agent = Agent(
        tools=tools or ALL_TOOLS,
        interventions=[cedar, temporal],
        callback_handler=lambda **kwargs: None,
    )
    result = agent(prompt)
    console.print(Panel(Markdown(str(result)), border_style=style))
    console.print()


if __name__ == "__main__":
    console.print(Panel(
        "[bold]Dogwood-Style Temporal Authorization with Strands[/]\n\n"
        "This demo combines Cedar point-in-time policies with a temporal\n"
        "event history tracker to simulate Dogwood's temporal conditions:\n\n"
        "  [cyan]formerly[/]     - SellShares requires prior ApproveSale\n"
        "  [cyan]count_within[/] - Max 5 transfers per hour\n"
        "  [cyan]sum_within[/]   - Max $5,000 transferred per hour\n\n"
        "Cedar handles basic authorization (share limits, action permits).\n"
        "The temporal handler adds history-dependent sequence checks.\n\n"
        "[dim]Dogwood repo: https://github.com/dogwood-policy/dogwood[/]",
        title="Demo",
        border_style="bright_blue",
    ))
    console.print()

    # Reset temporal store for clean demo
    _store.events.clear()

    # Scenario 1: Try to sell without approval -> DENIED by temporal policy
    # Only SellShares is available — the agent cannot self-approve.
    run_scenario(
        title="Sell without approval -> DENIED (formerly: no prior ApproveSale)",
        style="red",
        prompt="Sell 100 shares of AMZN stock",
        tools=[SellShares],
    )

    # Reset for next scenario
    _store.events.clear()

    # Scenario 2: Approve then sell -> ALLOWED
    run_scenario(
        title="Approve then sell -> ALLOWED (formerly: approval found)",
        style="green",
        prompt="First approve the sale of 100 shares of AMZN, then sell 100 shares of AMZN",
    )

    # Reset for next scenario
    _store.events.clear()

    # Scenario 3: Get stock info -> ALLOWED (no temporal constraint)
    run_scenario(
        title="Get stock info -> ALLOWED (no temporal constraint, pure Cedar)",
        style="cyan",
        prompt="Get stock information for AMZN",
    )

    # Scenario 4: Multiple transfers -> rate limit kicks in
    _store.events.clear()
    run_scenario(
        title="Multiple transfers -> rate limit (count_within after 5)",
        style="yellow",
        prompt="Transfer $100 to bob, then $200 to carol, then $150 to dave, "
               "then $300 to erin, then $100 to frank, then $50 to grace",
    )
