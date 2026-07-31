"""Bulk Discounts Cedar policy example.

Demonstrates authorization for applying bulk discounts where:
- Only Platinum-tier customers can apply bulk discounts
- Order quantity must be >= 50
- Limited edition and seasonal specials are excluded
"""

from __future__ import annotations

from collections.abc import Callable
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

_POLICIES = load_policies("./policies/bulk_discounts/bulk_discounts.cedar")

_ENTITIES = [
    {
        "uid": {"type": "AgentCore::OAuthUser", "id": "customer_001"},
        "attrs": {},
        "parents": [],
        "tags": {"customer_tier": "Platinum"},
    },
    {
        "uid": {"type": "AgentCore::OAuthUser", "id": "customer_002"},
        "attrs": {},
        "parents": [],
        "tags": {"customer_tier": "Gold"},
    },
    {
        "uid": {"type": "AgentCore::Resource", "id": "order_system"},
        "attrs": {},
        "parents": [],
    },
]


class BulkDiscountCedarAuthorization(InterventionHandler):
    """Cedar authorization handler for bulk discount operations."""

    name = "cedar-bulk-discount-authorization"

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
        principal = self._principal_resolver(invocation_state)

        if not principal or not principal.get("type") or not principal.get("id"):
            return Deny(reason="No principal identity found in invocation state")

        tool_name = event.tool_use["name"]
        tool_input = event.tool_use.get("input") or {}

        request = {
            "principal": f'AgentCore::OAuthUser::"{principal["id"]}"',
            "action": f'AgentCore::Action::"{tool_name}"',
            "resource": 'AgentCore::Resource::"order_system"',
            "context": {
                "input": tool_input,
            },
        }

        try:
            result = cedarpy.is_authorized(request, self._policies, self._entities)
        except Exception as e:
            return Deny(reason=f"Cedar evaluation failed: {e}")

        if not result.allowed:
            reasons = []
            customer_tier = invocation_state.get("customer_tier", "unknown")
            order_qty = tool_input.get("orderQuantity", 0)
            product_types = tool_input.get("productTypes", [])
            excluded = {"limited_edition", "seasonal_specials"}

            if customer_tier != "Platinum":
                reasons.append(f"Customer tier is '{customer_tier}', only Platinum is eligible.")
            if order_qty < 50:
                reasons.append(f"Order quantity is {order_qty}, minimum required is 50.")
            if excluded.intersection(product_types):
                blocked = excluded.intersection(product_types)
                reasons.append(f"Product types {sorted(blocked)} are excluded from bulk discounts.")
            if not reasons:
                reasons.append("Policy conditions not met.")
            return Deny(
                reason=f"Access denied for action '{tool_name}'. {' '.join(reasons)}"
            )

        return Proceed()


@tool
def ApplyBulkDiscount(orderQuantity: int, productTypes: list[str], discountPercent: float) -> str:
    """Apply a bulk discount to an order given the quantity and product types."""
    return (
        f"Bulk discount of {discountPercent}% applied to order "
        f"with {orderQuantity} items of types: {', '.join(productTypes)}"
    )


cedar = BulkDiscountCedarAuthorization(
    policies=_POLICIES,
    entities=_ENTITIES,
    principal_resolver=lambda state: (
        {"type": "OAuthUser", "id": state["user_id"]}
        if state.get("user_id")
        else None
    ),
)

ALL_TOOLS = [ApplyBulkDiscount]


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
        "[bold]Cedar Bulk Discount Policy[/]\n"
        "Policy: policies/bulk_discounts/bulk_discounts.cedar\n\n"
        "Rules:\n"
        "  - Only Platinum-tier customers can apply bulk discounts\n"
        "  - Order quantity must be >= 50\n"
        "  - Limited edition and seasonal specials are excluded",
        title="Demo",
    ))
    console.print()

    # Scenario 1: Platinum customer, 100 items, standard products - PERMITTED
    run_scenario(
        title="Customer 001 (Platinum): 100 standard items - PERMITTED",
        style="green",
        prompt="Apply a 15% bulk discount to an order of 100 items with product types: electronics, clothing",
        invocation_state={"user_id": "customer_001", "customer_tier": "Platinum"},
    )

    # Scenario 2: Platinum customer, 30 items (below threshold) - DENIED
    run_scenario(
        title="Customer 001 (Platinum): 30 items (below minimum) - DENIED",
        style="red",
        prompt="Apply a 10% bulk discount to an order of 30 items with product types: electronics",
        invocation_state={"user_id": "customer_001", "customer_tier": "Platinum"},
    )

    # Scenario 3: Gold customer, 100 items - DENIED (not Platinum)
    run_scenario(
        title="Customer 002 (Gold): 100 items - DENIED (wrong tier)",
        style="red",
        prompt="Apply a 15% bulk discount to an order of 100 items with product types: electronics",
        invocation_state={"user_id": "customer_002", "customer_tier": "Gold"},
    )

    # Scenario 4: Platinum customer, limited edition products - DENIED (excluded category)
    run_scenario(
        title="Customer 001 (Platinum): 60 limited_edition items - DENIED (excluded)",
        style="red",
        prompt="Apply a 20% bulk discount to an order of 60 items with product types: limited_edition",
        invocation_state={"user_id": "customer_001", "customer_tier": "Platinum"},
    )
