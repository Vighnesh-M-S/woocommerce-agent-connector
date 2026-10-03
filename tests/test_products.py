"""Tests for connector.tools.products, with the WooCommerce client mocked out."""

from __future__ import annotations

from unittest.mock import MagicMock

from connector.tools.products import get_product, list_products, search_products


def test_list_products_with_in_stock_only_filter() -> None:
    """list_products() sets stock_status=instock when in_stock_only=True."""
    client = MagicMock()
    client.get.return_value = [{"id": 1, "stock_status": "instock"}]

    result = list_products(client, in_stock_only=True, limit=10, offset=0)

    client.get.assert_called_once_with(
        "products", params={"per_page": 10, "offset": 0, "stock_status": "instock"}
    )
    assert result == [{"id": 1, "stock_status": "instock"}]


def test_list_products_without_in_stock_only_filter() -> None:
    """list_products() omits stock_status when in_stock_only=False."""
    client = MagicMock()
    client.get.return_value = [{"id": 1}, {"id": 2}]

    result = list_products(client, category="widgets", limit=10, offset=0)

    client.get.assert_called_once_with(
        "products", params={"per_page": 10, "offset": 0, "category": "widgets"}
    )
    assert result == [{"id": 1}, {"id": 2}]


def test_get_product_returns_correct_structure() -> None:
    """get_product() calls the products/{id} endpoint and returns the product dict."""
    client = MagicMock()
    client.get.return_value = {"id": 7, "name": "Widget", "stock_quantity": 5}

    result = get_product(client, product_id=7)

    client.get.assert_called_once_with("products/7")
    assert result == {"id": 7, "name": "Widget", "stock_quantity": 5}


def test_search_products() -> None:
    """search_products() maps query to the search param."""
    client = MagicMock()
    client.get.return_value = [{"id": 1, "name": "Blue Widget"}]

    result = search_products(client, query="widget", limit=15)

    client.get.assert_called_once_with("products", params={"search": "widget", "per_page": 15})
    assert result == [{"id": 1, "name": "Blue Widget"}]
