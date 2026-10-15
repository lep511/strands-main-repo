"""MCP Server (spec 2026-07-28) — FastMCP 4.

Customer service tools: list/lookup customers, view order history, process
refunds. Written for the sessionless 2026-07-28 protocol:

* Stateless, self-contained requests — no ``Mcp-Session-Id``, no
  ``initialize`` handshake; every request carries its own protocol version
  and capabilities in ``_meta``. FastMCP also answers ``server/discover``.
* Multi round-trip requests (SEP-2322) — ``process_refund`` is a *guard*
  tool: it returns an ``InputRequiredResult`` asking the user to confirm,
  and the client retries the call with the answer attached. There is no
  server-initiated back-channel any more.
* Gateway routing headers (SEP-2243) — clients send ``Mcp-Method`` and
  ``Mcp-Name``; the ``customer_id`` argument opts in to ``Mcp-Param-Customer-Id``
  via the ``x-mcp-header`` schema extension so an L7 gateway can route on it.
* Cacheable results (SEP-2549) — ``tools/list``, ``resources/list`` and
  friends carry ``ttlMs`` / ``cacheScope`` freshness hints.
* Tools are returned in a deterministic order for client-side caching.

Legacy (handshake-era) clients still work: FastMCP negotiates the best
mutual protocol per connection, and ``process_refund`` falls back to
``ctx.elicit`` on those connections.

Run: python -m agent_mcp.mcp_server
  or: uvicorn agent_mcp.mcp_server:app --port 8000
"""

from __future__ import annotations

import os
from typing import Annotated

from fastmcp import Context, FastMCP
from mcp.server.request_state import RequestStateSecurity
from mcp.types import (
    ElicitRequest,
    ElicitRequestFormParams,
    InputRequiredResult,
    ResourceTemplateReference,
    ToolAnnotations,
)
from mcp.types.version import MODERN_PROTOCOL_VERSIONS
from pydantic import Field

PROTOCOL_VERSION = "2026-07-28"

# ─── Mock Data ──────────────────────────────────────────────────────────────

CUSTOMERS = {
    "C-1001": {
        "name": "Sarah Johnson",
        "email": "sarah.johnson@email.com",
        "phone": "555-0142",
        "account_status": "active",
    },
    "C-1002": {
        "name": "Mike Chen",
        "email": "mike.chen@email.com",
        "phone": "555-0198",
        "account_status": "locked",
    },
    "C-1003": {
        "name": "Laura Martinez",
        "email": "laura.martinez@email.com",
        "phone": "555-0267",
        "account_status": "active",
    },
    "C-1004": {
        "name": "James Wright",
        "email": "james.wright@email.com",
        "phone": "555-0334",
        "account_status": "active",
    },
    "C-1005": {
        "name": "Priya Patel",
        "email": "priya.patel@email.com",
        "phone": "555-0411",
        "account_status": "suspended",
    },
}

ORDERS = {
    "C-1001": [
        {
            "order_id": "ORD-5521",
            "item": "Wireless Headphones",
            "amount": 79.99,
            "status": "Delivered",
            "order_date": "2026-04-20",
            "delivered_date": "2026-04-28",
            "tracking": "TRK-998877",
        },
        {
            "order_id": "ORD-5488",
            "item": "USB-C Hub",
            "amount": 45.00,
            "status": "Shipped",
            "order_date": "2026-05-01",
            "estimated_delivery": "2026-05-06",
            "tracking": "TRK-887766",
        },
    ],
    "C-1002": [
        {
            "order_id": "ORD-5390",
            "item": "Mechanical Keyboard",
            "amount": 149.99,
            "status": "Delayed",
            "order_date": "2026-04-15",
            "estimated_delivery": "2026-04-25",
            "tracking": "TRK-776655",
        },
    ],
    "C-1003": [
        {
            "order_id": "ORD-5602",
            "item": "27\" 4K Monitor",
            "amount": 399.99,
            "status": "Delivered",
            "order_date": "2026-03-10",
            "delivered_date": "2026-03-18",
            "tracking": "TRK-665544",
        },
        {
            "order_id": "ORD-5610",
            "item": "Monitor Arm",
            "amount": 54.99,
            "status": "Delivered",
            "order_date": "2026-03-12",
            "delivered_date": "2026-03-19",
            "tracking": "TRK-665590",
        },
    ],
    "C-1004": [
        {
            "order_id": "ORD-5678",
            "item": "Noise-Canceling Earbuds",
            "amount": 129.99,
            "status": "Processing",
            "order_date": "2026-05-10",
            "estimated_delivery": "2026-05-17",
            "tracking": "TRK-554433",
        },
    ],
    "C-1005": [
        {
            "order_id": "ORD-5701",
            "item": "Ergonomic Mouse",
            "amount": 69.99,
            "status": "Cancelled",
            "order_date": "2026-05-05",
            "tracking": "TRK-443322",
        },
        {
            "order_id": "ORD-5720",
            "item": "Laptop Stand",
            "amount": 39.99,
            "status": "Refunded",
            "order_date": "2026-04-28",
            "delivered_date": "2026-05-03",
            "tracking": "TRK-443388",
        },
    ],
}


def _find_order(order_id: str) -> dict | None:
    for orders in ORDERS.values():
        for order in orders:
            if order["order_id"] == order_id:
                return order
    return None


def _format_customer(customer: dict) -> str:
    return (
        f"Customer: {customer['name']}\n"
        f"Email: {customer['email']}\n"
        f"Phone: {customer['phone']}\n"
        f"Account Status: {customer['account_status']}"
    )


def _is_modern_protocol(ctx: Context) -> bool:
    """True when the connection negotiated the sessionless 2026-07-28 era."""
    rc = ctx.request_context
    return rc is not None and rc.protocol_version in MODERN_PROTOCOL_VERSIONS


def _request_state_security() -> RequestStateSecurity | None:
    """Shared key so any replica can unseal ``requestState`` between rounds.

    Unset → FastMCP uses an ephemeral process-local key, which is fine for a
    single process. Behind a load balancer every replica must get the same
    ``REQUEST_STATE_KEY`` (at least 32 bytes).
    """
    key = os.environ.get("REQUEST_STATE_KEY")
    if not key:
        return None
    return RequestStateSecurity(keys=[key.encode()])


# ─── MCP Server (FastMCP 4 — stateless modern protocol) ─────────────────────

mcp = FastMCP(
    name="customer-service-mcp",
    version="0.2.0",
    instructions=(
        "Customer service tools. Use list_customers to see all customer IDs, "
        "lookup_customer to find customer info, get_order_history to check "
        "orders, and process_refund for refunds. process_refund asks the "
        "user to confirm before any money moves."
    ),
    # SEP-2549: freshness hints on list/read results (ttlMs / cacheScope).
    cache_ttl=60,
    cache_scope="public",
    # SEP-2322: seal/unseal requestState across rounds and replicas.
    request_state_security=_request_state_security(),
)

# SEP-2243: opt this argument in as a routing header (Mcp-Param-Customer-Id)
# so gateways can dispatch without parsing the JSON-RPC body.
CustomerId = Annotated[
    str,
    Field(
        description="The customer ID, e.g. C-1001",
        json_schema_extra={"x-mcp-header": "Customer-Id"},
    ),
]


@mcp.tool(
    annotations=ToolAnnotations(
        title="List Customer IDs",
        read_only_hint=True,
        idempotent_hint=True,
    ),
)
async def list_customers() -> str:
    """List all customer IDs in the system."""
    if not CUSTOMERS:
        return "No customers found."
    lines = [f"{cid} — {info['name']}" for cid, info in sorted(CUSTOMERS.items())]
    return "\n".join(lines)


@mcp.tool(
    annotations=ToolAnnotations(
        title="Lookup Customer",
        read_only_hint=True,
        idempotent_hint=True,
    ),
)
async def lookup_customer(customer_id: CustomerId) -> str:
    """Look up a customer by their ID."""
    customer = CUSTOMERS.get(customer_id)
    if not customer:
        return f"No customer found with ID {customer_id}"
    return _format_customer(customer)


@mcp.tool(
    annotations=ToolAnnotations(
        title="Get Order History",
        read_only_hint=True,
        idempotent_hint=True,
    ),
)
async def get_order_history(customer_id: CustomerId) -> str:
    """Get order history for a customer."""
    orders = ORDERS.get(customer_id)
    if not orders:
        return f"No orders found for customer {customer_id}"
    lines = []
    for order in orders:
        line = (
            f"Order {order['order_id']}: {order['item']} — ${order['amount']:.2f} "
            f"[{order['status']}] Ordered: {order['order_date']} "
        )
        if order.get("delivered_date"):
            line += f"Delivered: {order['delivered_date']} "
        if order.get("estimated_delivery"):
            line += f"Est. Delivery: {order['estimated_delivery']} "
        line += f"Tracking: {order['tracking']}"
        lines.append(line)
    return "\n".join(lines)


@mcp.tool(
    annotations=ToolAnnotations(
        title="Process Refund",
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
    ),
)
async def process_refund(
    order_id: Annotated[str, Field(description="The order ID to refund, e.g. ORD-5521")],
    amount: Annotated[float, Field(description="The refund amount in dollars", gt=0)],
    ctx: Context,
) -> str | InputRequiredResult:
    """Process a refund for an order.

    The server asks the user to confirm before the refund is applied. On the
    2026-07-28 protocol this is a multi round-trip request: the first call
    returns ``input_required`` with an elicitation, the client collects the
    answer and retries the same call with ``inputResponses`` attached.
    """
    order = _find_order(order_id)
    if order is None:
        return f"No order found with ID {order_id}"
    if order["status"] in ("Refunded", "Cancelled"):
        return f"Order {order_id} is already {order['status'].lower()}; nothing to refund."

    message = (
        f"Refund ${amount:.2f} for order {order_id} ({order['item']}, "
        f"paid ${order['amount']:.2f})?"
    )

    if not _is_modern_protocol(ctx):
        # Handshake-era connection: the back-channel still exists.
        result = await ctx.elicit(message, response_type=bool)
        approved = result.action == "accept" and bool(result.data)
        return _apply_refund(order_id, amount, approved)

    # Modern protocol: guard pattern. Round 1 asks, round 2 reads the answer.
    responses = ctx.input_responses
    if responses is None or "confirm" not in responses:
        return InputRequiredResult(
            result_type="input_required",
            input_requests={
                "confirm": ElicitRequest(
                    method="elicitation/create",
                    params=ElicitRequestFormParams(
                        message=message,
                        requested_schema={
                            "type": "object",
                            "properties": {
                                "approve": {
                                    "type": "boolean",
                                    "title": "Approve refund",
                                    "description": "true to process the refund, false to abort",
                                }
                            },
                            "required": ["approve"],
                        },
                    ),
                )
            },
            # Opaque, sealed by FastMCP; handed back as ctx.request_state.
            request_state=f"{order_id}:{amount}",
        )

    answer = responses["confirm"]
    approved = answer.action == "accept" and bool((answer.content or {}).get("approve"))
    return _apply_refund(order_id, amount, approved)


def _apply_refund(order_id: str, amount: float, approved: bool) -> str:
    if not approved:
        return f"Refund NOT processed for order {order_id}: the user did not confirm."
    return f"Refund of ${amount:.2f} processed for order {order_id}. Expect 3-5 business days."


# ─── Resources ─────────────────────────────────────────────────────────────


@mcp.resource(
    "customer://{customer_id}",
    name="customer_record",
    title="Customer Record",
    description="A single customer's profile as plain text.",
    mime_type="text/plain",
)
async def customer_record(customer_id: str) -> str:
    customer = CUSTOMERS.get(customer_id)
    if not customer:
        return f"No customer found with ID {customer_id}"
    return _format_customer(customer)


# ─── Argument Completion ───────────────────────────────────────────────────


@mcp.completion
def complete_customer_id(ref, argument, context):
    """Autocomplete the customer_id of the customer:// resource template."""
    if isinstance(ref, ResourceTemplateReference) and argument.name == "customer_id":
        prefix = (argument.value or "").lower()
        return [cid for cid in sorted(CUSTOMERS) if cid.lower().startswith(prefix)]
    return None


# ASGI app for production. stateless_http=True: any replica behind a plain
# load balancer can serve any request (no session affinity).
app = mcp.http_app(stateless_http=True)


def main() -> None:
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8000"))
    try:
        mcp.run(transport="http", host=host, port=port, stateless_http=True)
    except KeyboardInterrupt:
        print("\nMCP server stopped.")


if __name__ == "__main__":
    main()
