"""MCP server exposing read-only WooCommerce tools to an Agent Studio agent.

Defines the 9 read primitives (orders, products, customers) as MCP tools
with full JSON Schema input validation, and dispatches tool calls to the
underlying connector functions. Credentials and the HTTP client are
created once at startup and reused for the lifetime of the server.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from dotenv import load_dotenv
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from connector.auth import load_credentials
from connector.client import WooCommerceClient
from connector.tools.customers import get_customer, list_customers, search_customers
from connector.tools.orders import get_order, list_orders, search_orders
from connector.tools.products import get_product, list_products, search_products

load_dotenv()

_client: WooCommerceClient | None = None


def _get_client() -> WooCommerceClient:
    """Return the module-level WooCommerceClient, creating it on first use.

    Credentials are loaded lazily (rather than at import time) so that
    `import mcp_server` never fails just because environment variables
    are not yet set; the failure instead surfaces at startup/first call.
    """
    global _client
    if _client is None:
        _client = WooCommerceClient(load_credentials())
    return _client


ORDER_STATUSES = [
    "pending",
    "processing",
    "on-hold",
    "completed",
    "cancelled",
    "refunded",
    "failed",
]

TOOLS: list[Tool] = [
    Tool(
        name="list_orders",
        description="List WooCommerce orders, optionally filtered by status or customer ID.",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ORDER_STATUSES,
                    "description": "Filter orders by this status.",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "maximum": 100,
                    "description": "Maximum number of orders to return.",
                },
                "offset": {
                    "type": "integer",
                    "default": 0,
                    "description": "Number of orders to skip before returning results.",
                },
                "customer_id": {
                    "type": "integer",
                    "description": "Restrict results to this customer's orders.",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="get_order",
        description="Fetch a single WooCommerce order by its ID.",
        inputSchema={
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "integer",
                    "description": "The WooCommerce order ID to fetch.",
                },
            },
            "required": ["order_id"],
        },
    ),
    Tool(
        name="search_orders",
        description="Search WooCommerce orders by customer email and/or a date range.",
        inputSchema={
            "type": "object",
            "properties": {
                "customer_email": {
                    "type": "string",
                    "description": "Customer email (or other free-text term) to search for.",
                },
                "date_from": {
                    "type": "string",
                    "description": "ISO 8601 datetime, e.g. 2024-01-01T00:00:00. Only orders created after this date are returned.",
                },
                "date_to": {
                    "type": "string",
                    "description": "ISO 8601 datetime, e.g. 2024-01-31T00:00:00. Only orders created before this date are returned.",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "description": "Maximum number of orders to return.",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="list_products",
        description="List WooCommerce products (inventory), optionally filtered by category or stock status.",
        inputSchema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category slug or ID to filter by.",
                },
                "in_stock_only": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, only return products currently in stock.",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "description": "Maximum number of products to return.",
                },
                "offset": {
                    "type": "integer",
                    "default": 0,
                    "description": "Number of products to skip before returning results.",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="get_product",
        description="Fetch a single WooCommerce product by its ID.",
        inputSchema={
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "integer",
                    "description": "The WooCommerce product ID to fetch.",
                },
            },
            "required": ["product_id"],
        },
    ),
    Tool(
        name="search_products",
        description="Search WooCommerce products by name, description, or SKU.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text search term.",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "description": "Maximum number of products to return.",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="list_customers",
        description="List WooCommerce customers.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "description": "Maximum number of customers to return.",
                },
                "offset": {
                    "type": "integer",
                    "default": 0,
                    "description": "Number of customers to skip before returning results.",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="get_customer",
        description="Fetch a single WooCommerce customer by their ID.",
        inputSchema={
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "integer",
                    "description": "The WooCommerce customer ID to fetch.",
                },
            },
            "required": ["customer_id"],
        },
    ),
    Tool(
        name="search_customers",
        description="Search WooCommerce customers by name or email.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text search term.",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "description": "Maximum number of customers to return.",
                },
            },
            "required": ["query"],
        },
    ),
]

_DISPATCH = {
    "list_orders": lambda args: list_orders(
        _get_client(),
        status=args.get("status"),
        limit=args.get("limit", 10),
        offset=args.get("offset", 0),
        customer_id=args.get("customer_id"),
    ),
    "get_order": lambda args: get_order(_get_client(), order_id=args["order_id"]),
    "search_orders": lambda args: search_orders(
        _get_client(),
        customer_email=args.get("customer_email"),
        date_from=args.get("date_from"),
        date_to=args.get("date_to"),
        limit=args.get("limit", 10),
    ),
    "list_products": lambda args: list_products(
        _get_client(),
        category=args.get("category"),
        in_stock_only=args.get("in_stock_only", False),
        limit=args.get("limit", 10),
        offset=args.get("offset", 0),
    ),
    "get_product": lambda args: get_product(_get_client(), product_id=args["product_id"]),
    "search_products": lambda args: search_products(
        _get_client(), query=args["query"], limit=args.get("limit", 10)
    ),
    "list_customers": lambda args: list_customers(
        _get_client(), limit=args.get("limit", 10), offset=args.get("offset", 0)
    ),
    "get_customer": lambda args: get_customer(_get_client(), customer_id=args["customer_id"]),
    "search_customers": lambda args: search_customers(
        _get_client(), query=args["query"], limit=args.get("limit", 10)
    ),
}


async def list_tools(
    ctx: ServerRequestContext[Any], params: PaginatedRequestParams | None
) -> ListToolsResult:
    """Return the full set of WooCommerce read-only tools this server exposes."""
    return ListToolsResult(tools=TOOLS)


async def call_tool(
    ctx: ServerRequestContext[Any], params: CallToolRequestParams
) -> CallToolResult:
    """Dispatch an MCP tool call to the matching connector function.

    Args:
        ctx: The request context provided by the MCP server runtime.
        params: The tool call request, with `name` matching a Tool in TOOLS
            and `arguments` validated against that tool's inputSchema.

    Returns:
        A CallToolResult wrapping a single TextContent with the
        JSON-serialised result of the underlying connector call.

    Raises:
        ValueError: If `params.name` does not match any known tool.
    """
    handler = _DISPATCH.get(params.name)
    if handler is None:
        raise ValueError(f"Unknown tool: {params.name}")

    result = handler(params.arguments or {})
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(result, default=str))]
    )


server = Server(
    "woocommerce-connector",
    on_list_tools=list_tools,
    on_call_tool=call_tool,
)


async def main() -> None:
    """Load credentials, create the WooCommerce client, and run the MCP server on stdio."""
    _get_client()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
