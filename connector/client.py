"""WooCommerce REST API client with Basic auth, retry, backoff, and rate limiting."""

from __future__ import annotations

import random
import time
from typing import Any

import httpx

from connector.auth import WooCommerceCredentials
from connector.rate_limiter import TokenBucketRateLimiter

API_PREFIX = "/wp-json/wc/v3"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_RETRY_ATTEMPTS = 3


class WooCommerceAPIError(RuntimeError):
    """Raised when the WooCommerce REST API returns a non-retryable error."""

    def __init__(self, status_code: int, body: str) -> None:
        """Store the HTTP status code and response body for the caller.

        Args:
            status_code: The HTTP status code returned by the API.
            body: The raw response body text returned by the API.
        """
        self.status_code = status_code
        self.body = body
        super().__init__(f"WooCommerce API error {status_code}: {body}")


class WooCommerceClient:
    """A persistent HTTP client for the WooCommerce REST API (v3).

    Wraps httpx.Client with Basic authentication, a request timeout,
    token-bucket rate limiting, and exponential backoff with jitter on
    HTTP 429 responses.
    """

    def __init__(
        self,
        credentials: WooCommerceCredentials,
        rate_limiter: TokenBucketRateLimiter | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Create a WooCommerce REST API client.

        Args:
            credentials: WooCommerce base URL and consumer key/secret.
            rate_limiter: Token bucket used to throttle outgoing requests.
                Defaults to a new limiter at 25 requests/second.
            timeout: Per-request timeout in seconds.
        """
        self._credentials = credentials
        self.rate_limiter = rate_limiter or TokenBucketRateLimiter(rate=25.0, capacity=25.0)
        self._http = httpx.Client(
            base_url=f"{credentials.base_url}{API_PREFIX}",
            auth=(credentials.consumer_key, credentials.consumer_secret),
            timeout=timeout,
        )

    def close(self) -> None:
        """Close the underlying persistent HTTP connection."""
        self._http.close()

    def __enter__(self) -> "WooCommerceClient":
        """Enter a context manager, returning this client."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Exit the context manager, closing the underlying HTTP client."""
        self.close()

    def _wait_for_rate_limiter(self) -> None:
        """Block briefly until the local token bucket allows a request."""
        while not self.rate_limiter.consume():
            time.sleep(1.0 / self.rate_limiter.rate)

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Issue a GET request against the WooCommerce REST API.

        Retries on HTTP 429 (rate limited) with exponential backoff and
        jitter, up to MAX_RETRY_ATTEMPTS attempts. Any other HTTP error
        status raises immediately with the status code and response body.

        Args:
            endpoint: API path relative to /wp-json/wc/v3, e.g. "orders".
            params: Optional query string parameters.

        Returns:
            The parsed JSON response body (dict or list, per endpoint).

        Raises:
            WooCommerceAPIError: If the API returns a non-2xx status that
                is not successfully retried.
        """
        self._wait_for_rate_limiter()

        last_error: WooCommerceAPIError | None = None
        for attempt in range(MAX_RETRY_ATTEMPTS):
            response = self._http.get(endpoint, params=params)

            if response.status_code == 429:
                last_error = WooCommerceAPIError(response.status_code, response.text)
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    backoff = (2**attempt) + random.uniform(0, 1)
                    time.sleep(backoff)
                    continue
                raise last_error

            if response.status_code >= 400:
                raise WooCommerceAPIError(response.status_code, response.text)

            return response.json()

        assert last_error is not None
        raise last_error
