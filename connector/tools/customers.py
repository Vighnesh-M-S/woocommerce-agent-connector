"""Read-only tools for WooCommerce customers."""

from __future__ import annotations

from typing import Any

from connector.client import WooCommerceClient


def list_customers(
    client: WooCommerceClient,
    limit: int = 10,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List WooCommerce customers.

    Args:
        client: An authenticated WooCommerceClient.
        limit: Maximum number of customers to return.
        offset: Number of customers to skip before returning results.

    Returns:
        A list of customer dicts as returned by the WooCommerce REST API.
    """
    params: dict[str, Any] = {"per_page": limit, "offset": offset}
    return client.get("customers", params=params)


def get_customer(client: WooCommerceClient, customer_id: int) -> dict[str, Any]:
    """Fetch a single WooCommerce customer by ID.

    Args:
        client: An authenticated WooCommerceClient.
        customer_id: The WooCommerce customer ID to fetch.

    Returns:
        The customer dict as returned by the WooCommerce REST API.
    """
    return client.get(f"customers/{customer_id}")


def search_customers(
    client: WooCommerceClient,
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search WooCommerce customers by name/email.

    Args:
        client: An authenticated WooCommerceClient.
        query: Free-text search term.
        limit: Maximum number of customers to return.

    Returns:
        A list of customer dicts as returned by the WooCommerce REST API.
    """
    params: dict[str, Any] = {"search": query, "per_page": limit}
    return client.get("customers", params=params)
