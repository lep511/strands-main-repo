"""MCP Server (spec 2026-07-28) — FastMCP 4 beta.

Customer service tools: lookup customers, view order history, process refunds.
Stateless design with gateway routing headers and response caching.

Run: python -m agent_mcp.mcp_server
  or: uvicorn agent_mcp.mcp_server:app --port 8000
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

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

# ─── MCP Server (FastMCP 4 — stateless modern protocol) ─────────────────────

mcp = FastMCP(
    name="customer-service-mcp",
    instructions=(
        "Customer service tools. Use list_customers to see all customer IDs, "
        "lookup_customer to find customer info, "
        "get_order_history to check orders, and process_refund for refunds."
    ),
    cache_ttl=60,
    cache_scope="public",
)


@mcp.tool(
    annotations=ToolAnnotations(
        title="List Customer IDs",
        readOnlyHint=True,
        idempotentHint=True,
    ),
)
async def list_customers() -> str:
    """List all customer IDs in the system."""
    if not CUSTOMERS:
        return "No customers found."
    lines = [f"{cid} — {info['name']}" for cid, info in CUSTOMERS.items()]
    return "\n".join(lines)


@mcp.tool(
    annotations=ToolAnnotations(
        title="Lookup Customer",
        readOnlyHint=True,
        idempotentHint=True,
    ),
)
async def lookup_customer(
    customer_id: Annotated[str, Field(description="The customer ID")],
) -> str:
    """Look up a customer by their ID."""
    customer = CUSTOMERS.get(customer_id)
    if not customer:
        return f"No customer found with ID {customer_id}"
    return (
        f"Customer: {customer['name']}\n"
        f"Email: {customer['email']}\n"
        f"Phone: {customer['phone']}\n"
        f"Account Status: {customer['account_status']}"
    )


@mcp.tool(
    annotations=ToolAnnotations(
        title="Get Order History",
        readOnlyHint=True,
        idempotentHint=True,
    ),
)
async def get_order_history(
    customer_id: Annotated[str, Field(description="The customer ID")],
) -> str:
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
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
    ),
)
async def process_refund(
    order_id: Annotated[str, Field(description="The order ID to refund")],
    amount: Annotated[float, Field(description="The refund amount in dollars", gt=0)],
    confirmed: Annotated[bool, Field(description="Must be true. Ask the user to confirm before calling with confirmed=true")],
) -> str:
    """Process a refund for an order. Requires explicit user confirmation."""
    if not confirmed:
        return f"Refund NOT processed. Please confirm with the user before calling with confirmed=true."
    return f"Refund of ${amount:.2f} processed for order {order_id}. Expect 3-5 business days."


# ─── Argument Completion ───────────────────────────────────────────────────

@mcp.completion
def complete_customer_id(ref, argument, context):
    """Autocomplete customer_id arguments across tools."""
    if argument.name == "customer_id":
        return [
            cid for cid in CUSTOMERS
            if cid.lower().startswith(argument.value.lower())
        ]
    return None


# ASGI app for production (stateless_http=True for load balancers)
app = mcp.http_app(stateless_http=True)


def main() -> None:
    try:
        mcp.run(transport="http", host="0.0.0.0", port=8000)
    except KeyboardInterrupt:
        print("\nMCP server stopped.")
