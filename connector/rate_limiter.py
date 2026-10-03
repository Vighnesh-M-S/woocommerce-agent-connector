"""Token bucket rate limiter used to throttle outgoing WooCommerce requests."""

from __future__ import annotations

import time


class TokenBucketRateLimiter:
    """A simple token bucket rate limiter.

    Tokens refill continuously at `rate` tokens per second up to a maximum
    of `capacity` tokens. Each call to consume() attempts to remove one
    token from the bucket.
    """

    def __init__(self, rate: float = 25.0, capacity: float = 25.0) -> None:
        """Initialize the rate limiter.

        Args:
            rate: Number of tokens added back to the bucket per second.
            capacity: Maximum number of tokens the bucket can hold.
        """
        self.rate = rate
        self.capacity = capacity
        self._tokens = capacity
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        """Add tokens to the bucket based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_refill = now

    def consume(self, tokens: float = 1.0) -> bool:
        """Attempt to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume for this call.

        Returns:
            True if enough tokens were available and have been consumed,
            False if the bucket does not currently have enough tokens
            (i.e. the caller is rate limited).
        """
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False
