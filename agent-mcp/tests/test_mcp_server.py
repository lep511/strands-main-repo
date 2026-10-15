"""Smoke tests for the customer-service MCP server on protocol 2026-07-28.

Uses the FastMCP in-memory transport, so no network is needed. The client
defaults to ``mode="auto"``, which negotiates the sessionless protocol.
"""

import pytest
from fastmcp import Client
from mcp.types import ElicitResult

from agent_mcp.mcp_server import mcp

MODERN = "2026-07-28"


async def test_negotiates_modern_protocol():
    async with Client(mcp) as client:
        assert client.protocol_version == MODERN
        assert client.server_info.name == "customer-service-mcp"


async def test_tools_listed_deterministically_with_cache_hints():
    async with Client(mcp) as client:
        first = await client.list_tools()
        second = await client.list_tools()
    names = [t.name for t in first]
    assert names == [t.name for t in second]
    assert set(names) == {"list_customers", "lookup_customer", "get_order_history", "process_refund"}


async def test_customer_id_opts_into_routing_header():
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
    prop = tools["lookup_customer"].input_schema["properties"]["customer_id"]
    assert prop["x-mcp-header"] == "Customer-Id"


async def test_lookup_customer():
    async with Client(mcp) as client:
        result = await client.call_tool("lookup_customer", {"customer_id": "C-1001"})
    assert "Sarah Johnson" in result.data


async def test_refund_requires_confirmation_round_trip():
    seen = []

    async def approve(message, response_type, params, context):
        seen.append(message)
        return ElicitResult(action="accept", content={"approve": True})

    async with Client(mcp, elicitation_handler=approve) as client:
        result = await client.call_tool("process_refund", {"order_id": "ORD-5521", "amount": 79.99})
    assert len(seen) == 1 and "ORD-5521" in seen[0]
    assert "processed" in result.data and "NOT" not in result.data


async def test_refund_declined():
    async def decline(message, response_type, params, context):
        return ElicitResult(action="decline")

    async with Client(mcp, elicitation_handler=decline) as client:
        result = await client.call_tool("process_refund", {"order_id": "ORD-5521", "amount": 79.99})
    assert "NOT processed" in result.data


async def test_customer_resource_and_completion():
    async with Client(mcp) as client:
        content = await client.read_resource("customer://C-1003")
        assert "Laura Martinez" in content[0].text
