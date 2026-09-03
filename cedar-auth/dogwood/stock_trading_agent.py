"""Dogwood Temporal Policy Simulator for a Stock Trading Agent.

Demonstrates Dogwood's temporal policy concepts by building a Python reference
implementation that simulates how temporal conditions (formerly, count_within,
sum_within, count_distinct_within, bind) evaluate against an event trace.

Dogwood extends Cedar with temporal clauses that look back over an agent's
recent events — not just the current request. This example uses the stock
trading agent scenario from the AWS blog post introducing Dogwood.

Policies are loaded from .dw files in the policies/ directory. The simulator
replays event traces and shows how each policy evaluates at each point in time.

Reference: https://github.com/dogwood-policy/dogwood
Blog: https://aws.amazon.com/blogs/opensource/introducing-dogwood-runtime-verification-for-ai-agents/
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

console = Console()


# ---------------------------------------------------------------------------
# Event model
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """A single event in a Dogwood trace — either a tool-call request or response."""
    timestamp: int
    action: str
    kind: str  # "request" or "response"
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthDecision:
    allowed: bool
    policy_id: str
    reason: str


# ---------------------------------------------------------------------------
# Temporal operators (reference implementation)
# ---------------------------------------------------------------------------

class TemporalEngine:
    """Evaluates Dogwood temporal operators against an event history.

    This mirrors the semantics described in the Dogwood language:
    - formerly(window, matcher): did a matching event occur within the window?
    - count_within(window, matcher): how many matching events in the window?
    - count_distinct_within(field, window, matcher): how many distinct values?
    - sum_within(field, window, matcher): sum of a numeric field in the window?
    - bind(name, aggregate, condition): name an aggregate for comparison.
    """

    def __init__(self):
        self.events: list[Event] = []

    def record(self, event: Event):
        self.events.append(event)

    def _events_in_window(self, now: int, window_seconds: int) -> list[Event]:
        cutoff = now - window_seconds
        return [e for e in self.events if e.timestamp >= cutoff and e.timestamp <= now]

    def formerly(
        self,
        now: int,
        window_seconds: int,
        action: str,
        kind: str,
        matcher: dict[str, Any],
    ) -> bool:
        for event in self._events_in_window(now, window_seconds):
            if event.action == action and event.kind == kind:
                if self._matches(event.data, matcher):
                    return True
        return False

    def count_within(
        self,
        now: int,
        window_seconds: int,
        action: str,
        kind: str,
        matcher: dict[str, Any] | None = None,
    ) -> int:
        count = 0
        for event in self._events_in_window(now, window_seconds):
            if event.action == action and event.kind == kind:
                if matcher is None or self._matches(event.data, matcher):
                    count += 1
        return count

    def count_distinct_within(
        self,
        field_name: str,
        now: int,
        window_seconds: int,
        action: str,
        kind: str,
    ) -> int:
        values = set()
        for event in self._events_in_window(now, window_seconds):
            if event.action == action and event.kind == kind:
                if field_name in event.data:
                    values.add(event.data[field_name])
        return len(values)

    def sum_within(
        self,
        field_name: str,
        now: int,
        window_seconds: int,
        action: str,
        kind: str,
    ) -> int:
        total = 0
        for event in self._events_in_window(now, window_seconds):
            if event.action == action and event.kind == kind:
                total += event.data.get(field_name, 0)
        return total

    @staticmethod
    def _matches(event_data: dict, matcher: dict) -> bool:
        for key, expected in matcher.items():
            if expected == "_":
                if key not in event_data:
                    return False
            elif event_data.get(key) != expected:
                return False
        return True


# ---------------------------------------------------------------------------
# Policy definitions (Python equivalents of the .dw files)
# ---------------------------------------------------------------------------

PolicyFn = Callable[[Event, TemporalEngine], AuthDecision]


def policy_approve_before_sell(request: Event, engine: TemporalEngine) -> AuthDecision:
    """approve_before_sell.dw — Permit SellShares only if ApproveSale for the
    same stock and shares came back approved within the last hour."""
    if request.action != "SellShares":
        return AuthDecision(False, "approve_before_sell", "Action not covered by this policy")

    approved = engine.formerly(
        now=request.timestamp,
        window_seconds=3600,
        action="ApproveSale",
        kind="response",
        matcher={
            "stock": request.data["stock"],
            "shares": request.data["shares"],
            "approved": True,
        },
    )
    if approved:
        return AuthDecision(True, "approve_before_sell", "Prior approval found within 1h")
    return AuthDecision(False, "approve_before_sell", "No matching approval in the last hour")


def policy_small_and_approved(request: Event, engine: TemporalEngine) -> AuthDecision:
    """small_and_approved.dw — Permit SellShares only if shares <= 100 (Cedar
    point-in-time) AND prior approval exists (temporal)."""
    if request.action != "SellShares":
        return AuthDecision(False, "small_and_approved", "Action not covered by this policy")

    if request.data.get("shares", 0) > 100:
        return AuthDecision(False, "small_and_approved", f"shares={request.data['shares']} exceeds 100")

    approved = engine.formerly(
        now=request.timestamp,
        window_seconds=3600,
        action="ApproveSale",
        kind="response",
        matcher={
            "stock": request.data["stock"],
            "shares": request.data["shares"],
            "approved": True,
        },
    )
    if approved:
        return AuthDecision(True, "small_and_approved", "Small sale with prior approval")
    return AuthDecision(False, "small_and_approved", "No matching approval in the last hour")


def policy_rate_limit_transfers(request: Event, engine: TemporalEngine) -> AuthDecision:
    """rate_limit_transfers.dw — Forbid Transfer once 5 have already gone out
    in the last hour."""
    if request.action != "Transfer":
        return AuthDecision(True, "rate_limit_transfers", "Action not subject to rate limit")

    count = engine.count_within(
        now=request.timestamp,
        window_seconds=3600,
        action="Transfer",
        kind="request",
    )
    if count > 5:
        return AuthDecision(False, "rate_limit_transfers", f"Rate limit: {count} transfers in window (max 5)")
    return AuthDecision(True, "rate_limit_transfers", f"Transfer #{count} within limit")


def policy_distinct_recipients(request: Event, engine: TemporalEngine) -> AuthDecision:
    """distinct_recipients_limit.dw — Forbid Transfer to a 4th distinct
    recipient in the last hour."""
    if request.action != "Transfer":
        return AuthDecision(True, "distinct_recipients", "Action not subject to this limit")

    distinct = engine.count_distinct_within(
        field_name="user",
        now=request.timestamp,
        window_seconds=3600,
        action="Transfer",
        kind="request",
    )
    if distinct > 3:
        return AuthDecision(False, "distinct_recipients", f"{distinct} distinct recipients (max 3)")
    return AuthDecision(True, "distinct_recipients", f"{distinct} distinct recipient(s) within limit")


def policy_dollar_cap(request: Event, engine: TemporalEngine) -> AuthDecision:
    """dollar_cap.dw — Forbid Transfer once more than $5,000 has been requested
    in the last hour."""
    if request.action != "Transfer":
        return AuthDecision(True, "dollar_cap", "Action not subject to dollar cap")

    total = engine.sum_within(
        field_name="amount",
        now=request.timestamp,
        window_seconds=3600,
        action="Transfer",
        kind="request",
    )
    if total > 5000:
        return AuthDecision(False, "dollar_cap", f"${total} total exceeds $5,000 cap")
    return AuthDecision(True, "dollar_cap", f"${total} total within $5,000 cap")


def policy_anti_spike(request: Event, engine: TemporalEngine) -> AuthDecision:
    """anti_spike.dw — Forbid a transfer larger than everything already settled
    in the last hour, combined. Uses bind() to name the aggregate."""
    if request.action != "Transfer":
        return AuthDecision(True, "anti_spike", "Action not subject to anti-spike")

    prior = engine.sum_within(
        field_name="amount",
        now=request.timestamp,
        window_seconds=3600,
        action="Transfer",
        kind="response",
    )
    amount = request.data.get("amount", 0)
    if amount > prior:
        return AuthDecision(False, "anti_spike", f"${amount} exceeds ${prior} settled")
    return AuthDecision(True, "anti_spike", f"${amount} within ${prior} settled")


# ---------------------------------------------------------------------------
# Trace replay engine
# ---------------------------------------------------------------------------

def replay_trace(
    title: str,
    policy_file: str,
    policy_fn: PolicyFn,
    events: list[Event],
):
    """Replay a sequence of events against a Dogwood temporal policy."""
    engine = TemporalEngine()

    console.rule(f"[bold cyan]{title}[/]")
    console.print(f"[dim]Policy: {policy_file}[/]")
    console.print()

    with open(f"./policies/{policy_file}") as f:
        policy_source = f.read()
    console.print(Panel(policy_source.strip(), title="[bold]Dogwood Policy (.dw)[/]", border_style="blue"))

    table = Table(title="Trace Replay", show_lines=True)
    table.add_column("Time", style="bold", width=8)
    table.add_column("Event", width=40)
    table.add_column("Verdict", width=10)
    table.add_column("Reason", width=45)

    for event in events:
        is_request = event.kind == "request"

        # Record the event BEFORE evaluation (requests include themselves)
        engine.record(event)

        if is_request:
            decision = policy_fn(event, engine)
            verdict_style = "green" if decision.allowed else "red"
            verdict_text = "ALLOW" if decision.allowed else "DENY"
            table.add_row(
                f"@{event.timestamp}",
                f"{event.action}::{event.kind}  {event.data}",
                f"[{verdict_style}]{verdict_text}[/]",
                decision.reason,
            )
        else:
            table.add_row(
                f"@{event.timestamp}",
                f"{event.action}::{event.kind}  {event.data}",
                "[dim]---[/]",
                "[dim]Response recorded in history[/]",
            )

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

def run_all_scenarios():
    console.print(Panel(
        "[bold]Dogwood Temporal Policy Simulator[/]\n\n"
        "Dogwood extends Cedar with temporal conditions that look back over an\n"
        "agent's recent events. This simulator demonstrates the key temporal\n"
        "operators using a stock trading agent scenario.\n\n"
        "Operators demonstrated:\n"
        "  formerly     - Did a matching event occur within a time window?\n"
        "  count_within - How many matching events in the window?\n"
        "  count_distinct_within - How many distinct values of a field?\n"
        "  sum_within   - Sum of a numeric field across events?\n"
        "  bind         - Name an aggregate for comparison\n\n"
        "[dim]Reference: https://github.com/dogwood-policy/dogwood[/]",
        title="Demo",
        border_style="bright_blue",
    ))
    console.print()

    # --- Scenario 1: Approve before sell (formerly) ---
    replay_trace(
        title="1. formerly: Approve Before You Sell",
        policy_file="approve_before_sell.dw",
        policy_fn=policy_approve_before_sell,
        events=[
            Event(0, "SellShares", "request", {"stock": "AMZN", "shares": 100}),
            Event(1700, "ApproveSale", "response", {"stock": "AMZN", "shares": 100, "approved": True}),
            Event(1800, "SellShares", "request", {"stock": "AMZN", "shares": 100}),
            Event(7200, "SellShares", "request", {"stock": "AMZN", "shares": 100}),
        ],
    )

    # --- Scenario 2: Small AND approved (mixed temporal + Cedar) ---
    replay_trace(
        title="2. Mixed Clauses: Small AND Recently Approved",
        policy_file="small_and_approved.dw",
        policy_fn=policy_small_and_approved,
        events=[
            Event(0, "SellShares", "request", {"stock": "AMZN", "shares": 50}),
            Event(60, "ApproveSale", "response", {"stock": "AMZN", "shares": 50, "approved": True}),
            Event(120, "SellShares", "request", {"stock": "AMZN", "shares": 50}),
            Event(180, "ApproveSale", "response", {"stock": "AMZN", "shares": 500, "approved": True}),
            Event(240, "SellShares", "request", {"stock": "AMZN", "shares": 500}),
        ],
    )

    # --- Scenario 3: Rate-limit transfers (count_within) ---
    replay_trace(
        title="3. count_within: Rate-Limit Transfers",
        policy_file="rate_limit_transfers.dw",
        policy_fn=policy_rate_limit_transfers,
        events=[
            Event(0, "Transfer", "request", {"amount": 20}),
            Event(60, "Transfer", "request", {"amount": 20}),
            Event(120, "Transfer", "request", {"amount": 20}),
            Event(180, "Transfer", "request", {"amount": 20}),
            Event(240, "Transfer", "request", {"amount": 20}),
            Event(300, "Transfer", "request", {"amount": 20}),
        ],
    )

    # --- Scenario 4: Distinct recipients (count_distinct_within) ---
    replay_trace(
        title="4. count_distinct_within: Limit Distinct Recipients",
        policy_file="distinct_recipients_limit.dw",
        policy_fn=policy_distinct_recipients,
        events=[
            Event(0, "Transfer", "request", {"user": "bob", "amount": 100}),
            Event(60, "Transfer", "request", {"user": "carol", "amount": 200}),
            Event(120, "Transfer", "request", {"user": "dave", "amount": 150}),
            Event(180, "Transfer", "request", {"user": "erin", "amount": 300}),
            Event(240, "Transfer", "request", {"user": "bob", "amount": 50}),
        ],
    )

    # --- Scenario 5: Dollar cap (sum_within) ---
    replay_trace(
        title="5. sum_within: Dollar Cap on Transfers",
        policy_file="dollar_cap.dw",
        policy_fn=policy_dollar_cap,
        events=[
            Event(0, "Transfer", "request", {"amount": 2000}),
            Event(60, "Transfer", "request", {"amount": 2000}),
            Event(120, "Transfer", "request", {"amount": 2000}),
            Event(180, "Transfer", "request", {"amount": 500}),
        ],
    )

    # --- Scenario 6: Anti-spike (bind) ---
    replay_trace(
        title="6. bind: Anti-Spike Protection",
        policy_file="anti_spike.dw",
        policy_fn=policy_anti_spike,
        events=[
            Event(0, "Transfer", "response", {"amount": 1000}),
            Event(60, "Transfer", "request", {"amount": 500}),
            Event(120, "Transfer", "request", {"amount": 2000}),
            Event(180, "Transfer", "request", {"amount": 800}),
        ],
    )

    console.rule("[bold bright_blue]Summary[/]")
    console.print()
    console.print(
        "Dogwood's temporal operators enable policies that go beyond point-in-time\n"
        "authorization. By examining an agent's event history, you can enforce:\n\n"
        "  [bold]formerly[/]              - Prerequisites (approve before acting)\n"
        "  [bold]count_within[/]          - Rate limits (max N actions per window)\n"
        "  [bold]count_distinct_within[/] - Diversity limits (max N distinct targets)\n"
        "  [bold]sum_within[/]            - Cumulative caps ($X total per window)\n"
        "  [bold]bind[/]                  - Relative thresholds (compare against history)\n\n"
        "All temporal operators use sliding time windows measured backward from\n"
        "the current request. Because Dogwood is a superset of Cedar, existing\n"
        "Cedar policies work as-is — temporal clauses are opt-in.\n"
    )


if __name__ == "__main__":
    run_all_scenarios()
