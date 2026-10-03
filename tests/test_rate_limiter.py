"""Tests for connector.rate_limiter.TokenBucketRateLimiter."""

from __future__ import annotations

import pytest

from connector.rate_limiter import TokenBucketRateLimiter


def test_consume_returns_true_when_tokens_available() -> None:
    """consume() succeeds while the bucket still has tokens."""
    limiter = TokenBucketRateLimiter(rate=25.0, capacity=25.0)

    assert limiter.consume() is True


def test_consume_returns_false_when_bucket_empty() -> None:
    """consume() fails once the bucket has been drained."""
    limiter = TokenBucketRateLimiter(rate=25.0, capacity=25.0)

    for _ in range(25):
        assert limiter.consume() is True

    assert limiter.consume() is False


def test_refill_over_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tokens are replenished based on elapsed monotonic time, not wall time."""
    fake_time = [1000.0]

    def fake_monotonic() -> float:
        return fake_time[0]

    monkeypatch.setattr("connector.rate_limiter.time.monotonic", fake_monotonic)

    limiter = TokenBucketRateLimiter(rate=10.0, capacity=10.0)

    for _ in range(10):
        assert limiter.consume() is True
    assert limiter.consume() is False

    fake_time[0] += 0.5  # 10 tokens/sec * 0.5s = 5 tokens refilled

    for _ in range(5):
        assert limiter.consume() is True
    assert limiter.consume() is False


def test_refill_never_exceeds_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refilling after a long idle period caps tokens at the bucket capacity."""
    fake_time = [1000.0]

    def fake_monotonic() -> float:
        return fake_time[0]

    monkeypatch.setattr("connector.rate_limiter.time.monotonic", fake_monotonic)

    limiter = TokenBucketRateLimiter(rate=25.0, capacity=25.0)
    limiter.consume()

    fake_time[0] += 1000.0

    for _ in range(25):
        assert limiter.consume() is True
    assert limiter.consume() is False
