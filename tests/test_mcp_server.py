"""Tests for the MCP layer: tool specification and dispatch through mcp_server."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator

import pytest
from mcp.types import CallToolRequestParams

import mcp_server
from connector.auth import WooCommerceCredentials
from connector.client import WooCommerceClient
from fake_store.server import FAKE_CONSUMER_KEY, FAKE_CONSUMER_SECRET, FakeWooCommerceServer

EXPECTED_TOOLS = {
    "list_orders": {"required": [], "properties": {"status", "limit", "offset", "customer_id"}},
    "get_order": {"required": ["order_id"], "properties": {"order_id"}},
    "search_orders": {"required": [], "properties": {"customer_email", "date_from", "date_to", "limit"}},
    "list_products": {"required": [], "properties": {"category", "in_stock_only", "limit", "offset"}},
    "get_product": {"required": ["product_id"], "properties": {"product_id"}},
    "search_products": {"required": ["query"], "properties": {"query", "limit"}},
    "list_customers": {"required": [], "properties": {"limit", "offset"}},
    "get_customer": {"required": ["customer_id"], "properties": {"customer_id"}},
    "search_customers": {"required": ["query"], "properties": {"query", "limit"}},
}


@pytest.fixture
def wired_server(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeWooCommerceServer]:
    """Point the MCP server's shared client at a fresh fake store."""
    monkeypatch.setattr("connector.client.time.sleep", lambda _seconds: None)
    with FakeWooCommerceServer() as store:
        creds = WooCommerceCredentials(
            base_url=store.base_url,
            consumer_key=FAKE_CONSUMER_KEY,
            consumer_secret=FAKE_CONSUMER_SECRET,
        )
        monkeypatch.setattr(mcp_server, "_client", WooCommerceClient(creds))
        yield store
        mcp_server._client.close()
        monkeypatch.setattr(mcp_server, "_client", None)


def test_tool_specification_matches_spec() -> None:
    """All 9 tools exist, with the required fields the spec calls for."""
    tools = {tool.name: tool for tool in mcp_server.TOOLS}

    assert set(tools) == set(EXPECTED_TOOLS)
    for name, expected in EXPECTED_TOOLS.items():
        schema = tools[name].input_schema
        assert schema["type"] == "object"
        assert set(schema["properties"]) == expected["properties"], name
        assert sorted(schema.get("required", [])) == sorted(expected["required"]), name


def test_list_orders_schema_has_status_enum() -> None:
    """list_orders restricts status to the WooCommerce status values and caps limit at 100."""
    schema = next(t for t in mcp_server.TOOLS if t.name == "list_orders").input_schema

    assert schema["properties"]["status"]["enum"] == mcp_server.ORDER_STATUSES
    assert schema["properties"]["limit"]["maximum"] == 100


def test_call_tool_returns_json_text(wired_server: FakeWooCommerceServer) -> None:
    """call_tool wraps the connector result as JSON text content."""
    params = CallToolRequestParams(name="get_order", arguments={"order_id": 102})

    result = asyncio.run(mcp_server.call_tool(None, params))

    assert len(result.content) == 1
    assert json.loads(result.content[0].text)["id"] == 102


def test_call_tool_unknown_name_raises(wired_server: FakeWooCommerceServer) -> None:
    """An unknown tool name fails with a clear error naming the tool."""
    params = CallToolRequestParams(name="delete_order", arguments={})

    with pytest.raises(ValueError, match="Unknown tool: delete_order"):
        asyncio.run(mcp_server.call_tool(None, params))


def test_every_tool_dispatches_successfully(wired_server: FakeWooCommerceServer) -> None:
    """Each of the 9 tools runs end to end against the fake store without error."""
    calls = {
        "list_orders": {},
        "get_order": {"order_id": 101},
        "search_orders": {"customer_email": "alice@example.com"},
        "list_products": {"in_stock_only": True},
        "get_product": {"product_id": 201},
        "search_products": {"query": "widget"},
        "list_customers": {},
        "get_customer": {"customer_id": 1},
        "search_customers": {"query": "bob"},
    }

    async def run_all() -> None:
        for name, arguments in calls.items():
            params = CallToolRequestParams(name=name, arguments=arguments)
            result = await mcp_server.call_tool(None, params)
            assert result.content[0].text

    asyncio.run(run_all())
    assert set(calls) == set(EXPECTED_TOOLS)
