"""Tests for connector.auth credential loading."""

from __future__ import annotations

import pytest

from connector.auth import MissingCredentialsError, load_credentials


def test_missing_all_env_vars_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """load_credentials() raises MissingCredentialsError naming every missing var."""
    monkeypatch.delenv("WC_BASE_URL", raising=False)
    monkeypatch.delenv("WC_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("WC_CONSUMER_SECRET", raising=False)

    with pytest.raises(MissingCredentialsError) as exc_info:
        load_credentials()

    message = str(exc_info.value)
    assert "WC_BASE_URL" in message
    assert "WC_CONSUMER_KEY" in message
    assert "WC_CONSUMER_SECRET" in message


def test_missing_one_env_var_raises_error_naming_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """load_credentials() raises and names only the specific var that is missing."""
    monkeypatch.setenv("WC_BASE_URL", "https://example.com")
    monkeypatch.setenv("WC_CONSUMER_KEY", "ck_test")
    monkeypatch.delenv("WC_CONSUMER_SECRET", raising=False)

    with pytest.raises(MissingCredentialsError) as exc_info:
        load_credentials()

    assert "WC_CONSUMER_SECRET" in str(exc_info.value)
    assert "WC_BASE_URL" not in str(exc_info.value)


def test_credentials_load_correctly_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """load_credentials() returns a WooCommerceCredentials populated from env vars."""
    monkeypatch.setenv("WC_BASE_URL", "https://example.com/")
    monkeypatch.setenv("WC_CONSUMER_KEY", "ck_abc123")
    monkeypatch.setenv("WC_CONSUMER_SECRET", "cs_xyz789")

    creds = load_credentials()

    assert creds.base_url == "https://example.com"
    assert creds.consumer_key == "ck_abc123"
    assert creds.consumer_secret == "cs_xyz789"
