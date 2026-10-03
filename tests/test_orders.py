"""Tests for connector.tools.orders, with the WooCommerce client mocked out."""

from __future__ import annotations

from unittest.mock import MagicMock

from connector.tools.orders import get_order, list_orders, search_orders


def test_list_orders_without_status_filter() -> None:
    """list_orders() omits the status param when none is given."""
    client = MagicMock()
    client.get.return_value = [{"id": 1}, {"id": 2}]

    result = list_orders(client, limit=5, offset=0)

    client.get.assert_called_once_with("orders", params={"per_page": 5, "offset": 0})
    assert result == [{"id": 1}, {"id": 2}]


def test_list_orders_with_status_filter() -> None:
    """list_orders() includes status and customer params when provided."""
    client = MagicMock()
    client.get.return_value = [{"id": 1, "status": "processing"}]

    result = list_orders(client, status="processing", limit=10, offset=0, customer_id=42)

    client.get.assert_called_once_with(
        "orders",
        params={"per_page": 10, "offset": 0, "status": "processing", "customer": 42},
    )
    assert result == [{"id": 1, "status": "processing"}]


def test_get_order_returns_correct_structure() -> None:
    """get_order() calls the orders/{id} endpoint and returns the order dict."""
    client = MagicMock()
    client.get.return_value = {"id": 99, "status": "completed", "total": "19.99"}

    result = get_order(client, order_id=99)

    client.get.assert_called_once_with("orders/99")
    assert result == {"id": 99, "status": "completed", "total": "19.99"}


def test_search_orders_with_email_filter() -> None:
    """search_orders() maps customer_email to the search param."""
    client = MagicMock()
    client.get.return_value = [{"id": 1, "billing": {"email": "a@example.com"}}]

    result = search_orders(client, customer_email="a@example.com", limit=10)

    client.get.assert_called_once_with(
        "orders", params={"per_page": 10, "search": "a@example.com"}
    )
    assert result == [{"id": 1, "billing": {"email": "a@example.com"}}]


def test_search_orders_with_date_range() -> None:
    """search_orders() maps date_from/date_to to after/before params."""
    client = MagicMock()
    client.get.return_value = []

    search_orders(
        client,
        date_from="2024-01-01T00:00:00",
        date_to="2024-01-31T00:00:00",
        limit=20,
    )

    client.get.assert_called_once_with(
        "orders",
        params={
            "per_page": 20,
            "after": "2024-01-01T00:00:00",
            "before": "2024-01-31T00:00:00",
        },
    )
