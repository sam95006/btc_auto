"""Centralized payment-provider selection for BILLING-4.

Routes must not construct providers directly or scatter env parsing. Provider
choice is decided here:

  * ``stripe``   -> StripePaymentProvider, only when a complete, SAFE (test-key)
    config is present. A live key or incomplete config yields None (disabled).
  * ``mock``     -> MockPaymentProvider, only when explicitly allowed (staging +
    opt-in).
  * anything else / unset -> None (disabled, fail closed).
"""

from __future__ import annotations

from typing import Optional

from backend.nexus_billing.mock_provider import MockPaymentProvider
from backend.nexus_billing.stripe_provider import (
    StripeConfig,
    StripeConfigError,
    StripePaymentProvider,
)


def build_payment_provider(env: dict[str, str], *, mock_allowed: bool = False):
    """Return the configured provider or None (disabled)."""
    name = (env.get("NEXUS_BILLING_PROVIDER") or "").strip().lower()
    if name == "stripe":
        config = StripeConfig.from_env(env)
        if config is None:
            return None
        try:
            return StripePaymentProvider(config)
        except StripeConfigError:
            # Unsafe config (e.g. live key) -> disabled, never a fallback.
            return None
    if name == "mock" and mock_allowed:
        return MockPaymentProvider()
    return None


def build_stripe_config(env: dict[str, str]) -> Optional[StripeConfig]:
    """Return a validated Stripe test config, or None if absent/unsafe."""
    config = StripeConfig.from_env(env)
    if config is None:
        return None
    try:
        config.validate()
    except StripeConfigError:
        return None
    return config
