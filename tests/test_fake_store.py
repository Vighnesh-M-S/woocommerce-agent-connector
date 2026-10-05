"""Integration tests: the real connector client talking to the in-process fake store."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from connector.auth import WooCommerceCredentials
from connector.client import WooCommerceAPIError, WooCommerceClient
from connector.tools.customers import search_customers
from connector.tools.orders import list_orders, search_orders
from connector.tools.products import list_products
from fake_store.server import FAKE_CONSUMER_KEY, FAKE_CONSUMER_SECRET, FakeWooCommerceServer


@pytest.fixture
def store() -> Iterator[FakeWooCommerceServer]:
    """Run a fresh fake WooCommerce store for each test."""
    with FakeWooCommerceServer() as server:
        yield server


@pytest.fixture
def client(store: FakeWooCommerceServer, monkeypatch: pytest.MonkeyPatch) -> Iterator[WooCommerceClient]:
    """Build a connector client pointed at the fake store, with retry sleeps disabled."""
    monkeypatch.setattr("connector.client.time.sleep", lambda _seconds: None)
    creds = WooCommerceCredentials(
        base_url=store.base_url,
        consumer_key=FAKE_CONSUMER_KEY,
        consumer_secret=FAKE_CONSUMER_SECRET,
    )
    with WooCommerceClient(creds) as connector_client:
        yield connector_client


def test_wrong_secret_is_rejected_with_401(store: FakeWooCommerceServer) -> None:
    """Basic auth with a wrong secret fails with the store's 401 status and body."""
    creds = WooCommerceCredentials(
        base_url=store.base_url,
        consumer_key=FAKE_CONSUMER_KEY,
        consumer_secret="cs_wrong",
    )
    with WooCommerceClient(creds) as bad_client, pytest.raises(WooCommerceAPIError) as exc_info:
        bad_client.get("orders")

    assert exc_info.value.status_code == 401
    assert "woocommerce_rest_authentication_error" in exc_info.value.body


def test_missing_auth_header_is_rejected(store: FakeWooCommerceServer) -> None:
    """A request without any credentials is rejected, not treated as anonymous."""
    import httpx

    response = httpx.get(f"{store.base_url}/wp-json/wc/v3/orders")

    assert response.status_code == 401


def test_list_orders_with_status_filter(client: WooCommerceClient) -> None:
    """list_orders returns only orders in the requested status."""
    orders = list_orders(client, status="processing")

    assert [o["id"] for o in orders] == [101]


def test_list_orders_pagination(client: WooCommerceClient) -> None:
    """list_orders honours per_page and offset."""
    first_page = list_orders(client, limit=2, offset=0)
    second_page = list_orders(client, limit=2, offset=2)

    assert [o["id"] for o in first_page] == [101, 102]
    assert [o["id"] for o in second_page] == [103, 104]


def test_search_orders_by_email_and_date(client: WooCommerceClient) -> None:
    """search_orders combines the email search with an ISO 8601 date lower bound."""
    orders = search_orders(client, customer_email="alice@example.com", date_from="2024-01-10T00:00:00")

    assert [o["id"] for o in orders] == [103]


def test_get_missing_order_raises_404(client: WooCommerceClient) -> None:
    """Fetching an unknown order ID raises WooCommerceAPIError with status 404."""
    with pytest.raises(WooCommerceAPIError) as exc_info:
        client.get("orders/999999")

    assert exc_info.value.status_code == 404


def test_list_products_in_stock_only(client: WooCommerceClient) -> None:
    """list_products with in_stock_only excludes out-of-stock items."""
    products = list_products(client, in_stock_only=True)

    assert [p["id"] for p in products] == [201, 203]


def test_search_customers_by_email(client: WooCommerceClient) -> None:
    """search_customers matches on email and returns the matching customer."""
    customers = search_customers(client, query="bob@example.com")

    assert [c["id"] for c in customers] == [2]


def test_429_is_retried_then_succeeds(store: FakeWooCommerceServer, client: WooCommerceClient) -> None:
    """Two forced 429s are retried, and the third attempt succeeds."""
    store.fail_next_with_429(2)
    before = store.request_count

    orders = list_orders(client, limit=1)

    assert len(orders) == 1
    assert store.request_count - before == 3


def test_persistent_429_gives_up_after_three_attempts(
    store: FakeWooCommerceServer, client: WooCommerceClient
) -> None:
    """If every attempt is rate limited, the client stops after 3 tries and raises 429."""
    store.fail_next_with_429(3)
    before = store.request_count

    with pytest.raises(WooCommerceAPIError) as exc_info:
        list_orders(client, limit=1)

    assert exc_info.value.status_code == 429
    assert store.request_count - before == 3
