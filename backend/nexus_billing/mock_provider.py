"""Deterministic in-memory Mock payment provider for BILLING-3.

Exists purely to validate the Billing architecture end to end. It makes ZERO
network requests, requires ZERO API keys, processes ZERO real money, stores ZERO
card data, and never calls Stripe or any external payment API. All identifiers
are obviously fake (``mock_*``).
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from backend.nexus_billing.provider import (
    BillingPortalSession,
    CancellationResult,
    CheckoutSession,
    ProviderEvent,
)

MOCK_PROVIDER_NAME = "mock"


class MockPaymentProvider:
    """A provider adapter that fabricates deterministic normalized events."""

    name = MOCK_PROVIDER_NAME

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counter = 0

    def _next(self, prefix: str) -> str:
        with self._lock:
            self._counter += 1
            return f"mock_{prefix}_{self._counter:06d}"

    def create_checkout_session(self, *, account_id: str, plan_code: str) -> CheckoutSession:
        checkout_id = self._next("checkout")
        return CheckoutSession(
            checkout_id=checkout_id,
            account_id=account_id,
            target_plan_code=plan_code,
            status="open",
            provider=self.name,
            # Deterministic, obviously-fake hosted checkout URL for the redirect
            # contract. No secrets, no real payment page.
            checkout_url=f"https://mock-checkout.local/{checkout_id}",
        )

    def make_event(
        self,
        *,
        account_id: str,
        event_type: str,
        target_plan_code: Optional[str] = None,
        provider_event_id: Optional[str] = None,
        provider_customer_id: Optional[str] = None,
        provider_subscription_id: Optional[str] = None,
    ) -> ProviderEvent:
        """Fabricate a normalized provider event (as a real adapter would emit).

        Mock customer/subscription ids are generated once and can be threaded
        through subsequent events to emulate a stable provider subscription.
        """
        return ProviderEvent(
            provider=self.name,
            provider_event_id=provider_event_id or self._next("event"),
            event_type=event_type,
            account_id=account_id,
            provider_customer_id=provider_customer_id or self._next("customer"),
            provider_subscription_id=provider_subscription_id or self._next("subscription"),
            target_plan_code=target_plan_code,
        )

    def request_subscription_cancellation(
        self, *, account_id: str, provider_subscription_id: Optional[str]
    ) -> CancellationResult:
        # Deterministic: request cancellation at period end. The authoritative
        # state change still arrives as a normalized provider event later.
        return CancellationResult(
            provider=self.name,
            status="cancellation_requested",
            cancel_at_period_end=True,
            provider_subscription_id=provider_subscription_id,
        )

    def create_billing_portal_session(
        self, *, account_id: str, provider_customer_id: Optional[str]
    ) -> BillingPortalSession:
        portal_id = self._next("portal")
        return BillingPortalSession(
            portal_id=portal_id,
            provider=self.name,
            portal_url=f"https://mock-portal.local/{portal_id}",
        )

    def normalize_event(self, raw: Any) -> ProviderEvent:
        # The mock already emits normalized ProviderEvents; a real adapter would
        # translate its own payload here. Never parses provider JSON in Core.
        if isinstance(raw, ProviderEvent):
            return raw
        raise ValueError("mock_provider_expects_provider_event")
