"""Credential loading for the WooCommerce REST API.

WooCommerce authenticates REST requests with a consumer key / consumer
secret pair sent as HTTP Basic auth over HTTPS. Credentials are never
hardcoded; they must be supplied via environment variables (optionally
loaded from a local .env file by the caller via python-dotenv).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

REQUIRED_ENV_VARS = ("WC_BASE_URL", "WC_CONSUMER_KEY", "WC_CONSUMER_SECRET")


class MissingCredentialsError(RuntimeError):
    """Raised when one or more required WooCommerce env vars are not set."""


@dataclass(frozen=True)
class WooCommerceCredentials:
    """Holds the WooCommerce site URL and REST API consumer credentials."""

    base_url: str
    consumer_key: str
    consumer_secret: str


def load_credentials() -> WooCommerceCredentials:
    """Load WooCommerce credentials from environment variables.

    Reads WC_BASE_URL, WC_CONSUMER_KEY, and WC_CONSUMER_SECRET from the
    process environment.

    Returns:
        A WooCommerceCredentials instance populated from the environment.

    Raises:
        MissingCredentialsError: If any required environment variable is
            missing or empty.
    """
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        raise MissingCredentialsError(
            "Missing required WooCommerce environment variable(s): "
            f"{', '.join(missing)}. Set them in your environment or in a "
            ".env file (see .env.example)."
        )

    return WooCommerceCredentials(
        base_url=os.environ["WC_BASE_URL"].rstrip("/"),
        consumer_key=os.environ["WC_CONSUMER_KEY"],
        consumer_secret=os.environ["WC_CONSUMER_SECRET"],
    )
