"""Read-only tools for WooCommerce orders."""

from __future__ import annotations

from typing import Any

from connector.client import WooCommerceClient


def list_orders(
    client: WooCommerceClient,
    status: str | None = None,
    limit: int = 10,
    offset: int = 0,
    customer_id: int | None = None,
) -> list[dict[str, Any]]:
    """List WooCommerce orders, optionally filtered by status or customer.

    Args:
        client: An authenticated WooCommerceClient.
        status: Order status to filter by (e.g. "processing"). Optional.
        limit: Maximum number of orders to return.
        offset: Number of orders to skip before returning results.
        customer_id: If provided, restrict results to this customer's orders.

    Returns:
        A list of order dicts as returned by the WooCommerce REST API.
    """
    params: dict[str, Any] = {"per_page": limit, "offset": offset}
    if status is not None:
        params["status"] = status
    if customer_id is not None:
        params["customer"] = customer_id

    return client.get("orders", params=params)


def get_order(client: WooCommerceClient, order_id: int) -> dict[str, Any]:
    """Fetch a single WooCommerce order by ID.

    Args:
        client: An authenticated WooCommerceClient.
        order_id: The WooCommerce order ID to fetch.

    Returns:
        The order dict as returned by the WooCommerce REST API.
    """
    return client.get(f"orders/{order_id}")


def search_orders(
    client: WooCommerceClient,
    customer_email: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search WooCommerce orders by customer email and/or date range.

    Args:
        client: An authenticated WooCommerceClient.
        customer_email: Free-text search term, typically a customer email.
        date_from: ISO 8601 datetime (e.g. "2024-01-01T00:00:00"); only
            orders created after this date are returned.
        date_to: ISO 8601 datetime (e.g. "2024-01-31T00:00:00"); only
            orders created before this date are returned.
        limit: Maximum number of orders to return.

    Returns:
        A list of order dicts as returned by the WooCommerce REST API.
    """
    params: dict[str, Any] = {"per_page": limit}
    if customer_email is not None:
        params["search"] = customer_email
    if date_from is not None:
        params["after"] = date_from
    if date_to is not None:
        params["before"] = date_to

    return client.get("orders", params=params)
