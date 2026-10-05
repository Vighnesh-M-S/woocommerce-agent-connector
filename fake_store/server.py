"""In-memory fake of the WooCommerce REST API v3, for offline demos and tests.

This server implements just enough of the WooCommerce REST contract for the
connector to run end to end without Docker or a live store:

* HTTP Basic auth against a fixed consumer key/secret pair
* ``GET /orders``, ``/products``, ``/customers`` (list) and ``/<resource>/<id>`` (get)
* the query params the connector sends: ``per_page``, ``offset``, ``status``,
  ``customer``, ``search``, ``after``, ``before``, ``category``, ``stock_status``
* an optional number of forced HTTP 429 responses, to exercise retry/backoff

It is not a WooCommerce replacement. It does not reproduce WooCommerce's
full response shape or its search ranking. Use it to test the connector's
own logic, not to certify compatibility with a real store.
"""

from __future__ import annotations

import base64
import binascii
import copy
import hmac
import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

API_PREFIX = "/wp-json/wc/v3/"
FAKE_CONSUMER_KEY = "ck_fake_demo_key"
FAKE_CONSUMER_SECRET = "cs_fake_demo_secret"
MAX_PER_PAGE = 100

ORDERS: list[dict[str, Any]] = [
    {
        "id": 101,
        "status": "processing",
        "currency": "USD",
        "total": "59.98",
        "date_created": "2024-01-05T10:00:00",
        "customer_id": 1,
        "billing": {"first_name": "Alice", "last_name": "Example", "email": "alice@example.com"},
        "line_items": [{"product_id": 201, "name": "Blue Widget", "quantity": 2, "total": "59.98"}],
    },
    {
        "id": 102,
        "status": "completed",
        "currency": "USD",
        "total": "24.50",
        "date_created": "2024-01-20T12:30:00",
        "customer_id": 2,
        "billing": {"first_name": "Bob", "last_name": "Builder", "email": "bob@example.com"},
        "line_items": [{"product_id": 203, "name": "Green Gizmo", "quantity": 1, "total": "24.50"}],
    },
    {
        "id": 103,
        "status": "on-hold",
        "currency": "USD",
        "total": "120.00",
        "date_created": "2024-02-02T09:15:00",
        "customer_id": 1,
        "billing": {"first_name": "Alice", "last_name": "Example", "email": "alice@example.com"},
        "line_items": [{"product_id": 203, "name": "Green Gizmo", "quantity": 4, "total": "120.00"}],
    },
    {
        "id": 104,
        "status": "refunded",
        "currency": "USD",
        "total": "15.00",
        "date_created": "2024-03-10T16:45:00",
        "customer_id": 0,
        "billing": {"first_name": "Guest", "last_name": "Shopper", "email": "guest@example.com"},
        "line_items": [{"product_id": 202, "name": "Red Gadget", "quantity": 1, "total": "15.00"}],
    },
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 201,
        "name": "Blue Widget",
        "sku": "BW-001",
        "price": "29.99",
        "status": "publish",
        "stock_status": "instock",
        "stock_quantity": 14,
        "categories": [{"id": 11, "slug": "widgets", "name": "Widgets"}],
    },
    {
        "id": 202,
        "name": "Red Gadget",
        "sku": "RG-002",
        "price": "15.00",
        "status": "publish",
        "stock_status": "outofstock",
        "stock_quantity": 0,
        "categories": [{"id": 12, "slug": "gadgets", "name": "Gadgets"}],
    },
    {
        "id": 203,
        "name": "Green Gizmo",
        "sku": "GG-003",
        "price": "24.50",
        "status": "publish",
        "stock_status": "instock",
        "stock_quantity": 5,
        "categories": [{"id": 12, "slug": "gadgets", "name": "Gadgets"}],
    },
]

CUSTOMERS: list[dict[str, Any]] = [
    {
        "id": 1,
        "email": "alice@example.com",
        "first_name": "Alice",
        "last_name": "Example",
        "username": "alice",
        "orders_count": 2,
    },
    {
        "id": 2,
        "email": "bob@example.com",
        "first_name": "Bob",
        "last_name": "Builder",
        "username": "bob",
        "orders_count": 1,
    },
]

COLLECTIONS: dict[str, list[dict[str, Any]]] = {
    "orders": ORDERS,
    "products": PRODUCTS,
    "customers": CUSTOMERS,
}


@dataclass
class _ServerState:
    """Mutable state shared between the HTTP handler threads and the test/demo caller."""

    consumer_key: str
    consumer_secret: str
    pending_429: int = 0
    request_count: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


def _error(code: str, message: str, status: int) -> dict[str, Any]:
    """Build a WooCommerce-style error body.

    Args:
        code: Machine-readable error code.
        message: Human-readable error message.
        status: HTTP status code, repeated inside the body as WooCommerce does.

    Returns:
        A dict shaped like a WooCommerce REST error response.
    """
    return {"code": code, "message": message, "data": {"status": status}}


def _limit(query: dict[str, str]) -> tuple[int, int]:
    """Read per_page and offset from the query, applying WooCommerce's bounds.

    Args:
        query: Flattened query-string parameters.

    Returns:
        A (per_page, offset) tuple. per_page is clamped to 1..100.
    """
    per_page = min(max(int(query.get("per_page", 10)), 1), MAX_PER_PAGE)
    offset = max(int(query.get("offset", 0)), 0)
    return per_page, offset


def _filter_orders(query: dict[str, str]) -> list[dict[str, Any]]:
    """Filter the order list using the query params the connector sends.

    Args:
        query: Flattened query-string parameters (status, customer, search, after, before).

    Returns:
        The matching orders, before pagination.
    """
    results = ORDERS
    if "status" in query:
        results = [o for o in results if o["status"] == query["status"]]
    if "customer" in query:
        results = [o for o in results if o["customer_id"] == int(query["customer"])]
    if "search" in query:
        term = query["search"].lower()
        results = [o for o in results if term in o["billing"]["email"].lower()]
    if "after" in query:
        results = [o for o in results if o["date_created"] > query["after"]]
    if "before" in query:
        results = [o for o in results if o["date_created"] < query["before"]]
    return results


def _filter_products(query: dict[str, str]) -> list[dict[str, Any]]:
    """Filter the product list using the query params the connector sends.

    Args:
        query: Flattened query-string parameters (category, stock_status, search).

    Returns:
        The matching products, before pagination.
    """
    results = PRODUCTS
    if "category" in query:
        results = [
            p for p in results if any(c["slug"] == query["category"] for c in p["categories"])
        ]
    if "stock_status" in query:
        results = [p for p in results if p["stock_status"] == query["stock_status"]]
    if "search" in query:
        term = query["search"].lower()
        results = [
            p for p in results if term in p["name"].lower() or term in p["sku"].lower()
        ]
    return results


def _filter_customers(query: dict[str, str]) -> list[dict[str, Any]]:
    """Filter the customer list using the query params the connector sends.

    Args:
        query: Flattened query-string parameters (search).

    Returns:
        The matching customers, before pagination.
    """
    results = CUSTOMERS
    if "search" in query:
        term = query["search"].lower()
        results = [
            c
            for c in results
            if term in c["email"].lower()
            or term in c["first_name"].lower()
            or term in c["last_name"].lower()
        ]
    return results


_FILTERS = {
    "orders": _filter_orders,
    "products": _filter_products,
    "customers": _filter_customers,
}


def _route(resource: str, query: dict[str, str]) -> tuple[int, Any]:
    """Resolve a resource path such as "orders" or "orders/101" to a response.

    Args:
        resource: Path relative to the API prefix, without leading slash.
        query: Flattened query-string parameters.

    Returns:
        A (status_code, json_body) tuple.
    """
    parts = resource.strip("/").split("/")
    collection = parts[0]
    if collection not in COLLECTIONS:
        return 404, _error("rest_no_route", "No route was found matching the URL for the request.", 404)

    if len(parts) == 1:
        per_page, offset = _limit(query)
        matches = _FILTERS[collection](query)
        return 200, copy.deepcopy(matches[offset : offset + per_page])

    if len(parts) == 2 and parts[1].isdigit():
        record_id = int(parts[1])
        for record in COLLECTIONS[collection]:
            if record["id"] == record_id:
                return 200, copy.deepcopy(record)
        return 404, _error(f"woocommerce_rest_{collection}_invalid_id", "Invalid ID.", 404)

    return 404, _error("rest_no_route", "No route was found matching the URL for the request.", 404)


class _Handler(BaseHTTPRequestHandler):
    """Request handler implementing auth, rate-limit injection, and routing."""

    server: ThreadingHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        """Silence the default per-request stderr logging."""
        return

    def do_GET(self) -> None:
        """Handle every GET request by routing it through the WooCommerce contract."""
        state: _ServerState = self.server.state  # type: ignore[attr-defined]
        parsed = urlparse(self.path)

        with state.lock:
            state.request_count += 1
            force_429 = state.pending_429 > 0
            if force_429:
                state.pending_429 -= 1

        if not parsed.path.startswith(API_PREFIX):
            self._send(404, _error("rest_no_route", "No route was found matching the URL for the request.", 404))
            return

        if not self._authorized(state):
            self._send(
                401,
                _error(
                    "woocommerce_rest_authentication_error",
                    "Invalid signature - provided signature does not match.",
                    401,
                ),
            )
            return

        if force_429:
            self._send(429, _error("rate_limited", "Too many requests.", 429))
            return

        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        status, body = _route(parsed.path[len(API_PREFIX) :], query)
        self._send(status, body)

    def _authorized(self, state: _ServerState) -> bool:
        """Check the Authorization header against the expected key and secret.

        Args:
            state: The shared server state holding the expected credentials.

        Returns:
            True if the Basic credentials match, otherwise False.
        """
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[len("Basic ") :]).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return False
        key, _, secret = decoded.partition(":")
        return hmac.compare_digest(key, state.consumer_key) and hmac.compare_digest(
            secret, state.consumer_secret
        )

    def _send(self, status: int, body: Any) -> None:
        """Write a JSON response with the given status code.

        Args:
            status: HTTP status code to send.
            body: JSON-serialisable response body.
        """
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class FakeWooCommerceServer:
    """Runs the fake WooCommerce REST API on a local port in a background thread."""

    def __init__(
        self,
        consumer_key: str = FAKE_CONSUMER_KEY,
        consumer_secret: str = FAKE_CONSUMER_SECRET,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        """Create the server without starting it.

        Args:
            consumer_key: The consumer key clients must present.
            consumer_secret: The consumer secret clients must present.
            host: Interface to bind to. Defaults to loopback only.
            port: Port to bind to. 0 picks a free port.
        """
        self._httpd = ThreadingHTTPServer((host, port), _Handler)
        self._httpd.state = _ServerState(  # type: ignore[attr-defined]
            consumer_key=consumer_key, consumer_secret=consumer_secret
        )
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        """The base URL clients should use, e.g. http://127.0.0.1:54321."""
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def request_count(self) -> int:
        """Total number of requests received, including rejected ones."""
        state: _ServerState = self._httpd.state  # type: ignore[attr-defined]
        with state.lock:
            return state.request_count

    def fail_next_with_429(self, count: int) -> None:
        """Make the next `count` authorized requests return HTTP 429.

        Args:
            count: How many upcoming requests should be rate limited.
        """
        state: _ServerState = self._httpd.state  # type: ignore[attr-defined]
        with state.lock:
            state.pending_429 = count

    def start(self) -> "FakeWooCommerceServer":
        """Start serving requests in a background thread.

        Returns:
            This server, so calls can be chained.
        """
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        """Stop serving and release the port."""
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def __enter__(self) -> "FakeWooCommerceServer":
        """Start the server when entering a `with` block."""
        return self.start()

    def __exit__(self, *exc_info: object) -> None:
        """Stop the server when leaving a `with` block."""
        self.stop()
