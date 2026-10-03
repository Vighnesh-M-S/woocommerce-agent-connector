"""Read-only tools for WooCommerce products (inventory)."""

from __future__ import annotations

from typing import Any

from connector.client import WooCommerceClient


def list_products(
    client: WooCommerceClient,
    category: str | None = None,
    in_stock_only: bool = False,
    limit: int = 10,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List WooCommerce products, optionally filtered by category or stock.

    Args:
        client: An authenticated WooCommerceClient.
        category: Category slug or ID to filter by. Optional.
        in_stock_only: If True, only return products with stock_status=instock.
        limit: Maximum number of products to return.
        offset: Number of products to skip before returning results.

    Returns:
        A list of product dicts as returned by the WooCommerce REST API.
    """
    params: dict[str, Any] = {"per_page": limit, "offset": offset}
    if category is not None:
        params["category"] = category
    if in_stock_only:
        params["stock_status"] = "instock"

    return client.get("products", params=params)


def get_product(client: WooCommerceClient, product_id: int) -> dict[str, Any]:
    """Fetch a single WooCommerce product by ID.

    Args:
        client: An authenticated WooCommerceClient.
        product_id: The WooCommerce product ID to fetch.

    Returns:
        The product dict as returned by the WooCommerce REST API.
    """
    return client.get(f"products/{product_id}")


def search_products(
    client: WooCommerceClient,
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search WooCommerce products by name/description/SKU.

    Args:
        client: An authenticated WooCommerceClient.
        query: Free-text search term.
        limit: Maximum number of products to return.

    Returns:
        A list of product dicts as returned by the WooCommerce REST API.
    """
    params: dict[str, Any] = {"search": query, "per_page": limit}
    return client.get("products", params=params)
