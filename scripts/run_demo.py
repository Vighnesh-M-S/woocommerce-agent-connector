"""Offline end-to-end demo of the WooCommerce connector.

Starts the in-process fake WooCommerce store, points the connector at it via
environment variables, and runs every MCP tool once. Also shows the two most
important failure paths: wrong credentials and an unknown tool name.

Run from the repository root:

    python scripts/run_demo.py

No Docker, no live store, and no real credentials are needed.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fake_store.server import FAKE_CONSUMER_KEY, FAKE_CONSUMER_SECRET, FakeWooCommerceServer  # noqa: E402


DEMO_CALLS: list[tuple[str, dict[str, Any]]] = [
    ("list_orders", {"status": "processing"}),
    ("get_order", {"order_id": 102}),
    ("search_orders", {"customer_email": "alice@example.com", "date_from": "2024-01-01T00:00:00"}),
    ("list_products", {"in_stock_only": True}),
    ("get_product", {"product_id": 203}),
    ("search_products", {"query": "gizmo"}),
    ("list_customers", {"limit": 5}),
    ("get_customer", {"customer_id": 2}),
    ("search_customers", {"query": "alice"}),
]


async def run_demo(base_url: str) -> None:
    """Call each MCP tool once against the fake store and print a summary.

    Args:
        base_url: Base URL of the running fake WooCommerce server.
    """
    import mcp_server

    tools = await mcp_server.list_tools(None, None)
    print(f"MCP server exposes {len(tools.tools)} tools: {', '.join(t.name for t in tools.tools)}\n")

    from mcp.types import CallToolRequestParams

    for name, arguments in DEMO_CALLS:
        result = await mcp_server.call_tool(None, CallToolRequestParams(name=name, arguments=arguments))
        payload = json.loads(result.content[0].text)
        summary = (
            f"{len(payload)} item(s)" if isinstance(payload, list) else f"id={payload.get('id')}"
        )
        print(f"  {name:<17} {json.dumps(arguments):<55} -> {summary}")

    print("\nFailure path 1: wrong consumer secret")
    from connector.auth import WooCommerceCredentials
    from connector.client import WooCommerceAPIError, WooCommerceClient

    bad = WooCommerceClient(
        WooCommerceCredentials(base_url=base_url, consumer_key=FAKE_CONSUMER_KEY, consumer_secret="cs_wrong")
    )
    try:
        bad.get("orders")
    except WooCommerceAPIError as exc:
        print(f"  rejected as expected: HTTP {exc.status_code}")
    finally:
        bad.close()

    print("\nFailure path 2: unknown tool name")
    try:
        await mcp_server.call_tool(None, CallToolRequestParams(name="delete_order", arguments={}))
    except ValueError as exc:
        print(f"  rejected as expected: {exc}")


def main() -> None:
    """Start the fake store, configure the connector to use it, and run the demo."""
    with FakeWooCommerceServer() as store:
        os.environ["WC_BASE_URL"] = store.base_url
        os.environ["WC_CONSUMER_KEY"] = FAKE_CONSUMER_KEY
        os.environ["WC_CONSUMER_SECRET"] = FAKE_CONSUMER_SECRET
        print(f"Fake WooCommerce store running at {store.base_url}\n")
        asyncio.run(run_demo(store.base_url))


if __name__ == "__main__":
    main()
