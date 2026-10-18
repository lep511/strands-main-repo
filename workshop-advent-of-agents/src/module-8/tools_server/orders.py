"""The order backend behind the gateway (~ the MCP server of the original).

One endpoint bundles a safe read tool with two high-risk ones, which is exactly the
situation Day 8 is about. If a call reaches this code, the tool RUNS: nothing here
checks permissions. The gateway policy is the only thing standing in the way.
"""

import json
from datetime import UTC, datetime

ORDERS = {
    "ORD-1001": {"status": "shipped", "carrier": "UPS", "tracking": "1Z999AA10123456784", "total": 129.99, "customer_id": "C-501"},
    "ORD-1002": {"status": "processing", "carrier": None, "tracking": None, "total": 54.50, "customer_id": "C-502"},
    "ORD-1003": {"status": "delivered", "carrier": "FedEx", "tracking": "449044304137821", "total": 310.00, "customer_id": "C-501"},
}


def lookup_order(order_id: str) -> dict:
    """Check order status and tracking details."""
    order = ORDERS.get(order_id.strip().upper())
    return {"order_id": order_id, **order} if order else {"error": f"order {order_id} not found"}


def issue_refund(order_id: str, amount: float, reason: str = "Customer Request") -> dict:
    """CRITICAL: Process a monetary refund for an order."""
    print(json.dumps({"EXECUTED": "issue_refund", "order_id": order_id, "amount": amount, "reason": reason}), flush=True)
    return {"status": "REFUNDED", "order_id": order_id, "amount": amount, "at": datetime.now(UTC).isoformat()}


def delete_account(customer_id: str) -> dict:
    """CRITICAL: Permanently delete a customer record."""
    print(json.dumps({"EXECUTED": "delete_account", "customer_id": customer_id}), flush=True)
    return {"status": "DELETED", "customer_id": customer_id, "at": datetime.now(UTC).isoformat()}


TOOLS = [lookup_order, issue_refund, delete_account]
