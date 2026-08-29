"""Provider-neutral payment abstraction for BILLING-3.

The rest of the application must not know which payment provider is in use.
Adapters (Mock now, real providers in BILLING-4) normalize their own payloads
into these types; Billing Core never parses provider-specific JSON.

No real provider, no network, no secrets are part of this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

# Normalized provider event types (internal, provider-neutral).
EVENT_CHECKOUT_COMPLETED = "checkout_completed"
EVENT_PAYMENT_FAILED = "payment_failed"
EVENT_PAYMENT_RECOVERED = "payment_recovered"
EVENT_SUBSCRIPTION_CANCELED = "subscription_canceled"
EVENT_SUBSCRIPTION_EXPIRED = "subscription_expired"
# Status-driven subscription events (used by adapters like Stripe whose
# subscription.* events carry a status rather than a single semantic action).
EVENT_SUBSCRIPTION_ACTIVE = "subscription_active"
EVENT_SUBSCRIPTION_TRIALING = "subscription_trialing"
EVENT_SUBSCRIPTION_PAST_DUE = "subscription_past_due"

KNOWN_EVENT_TYPES: frozenset[str] = frozenset(
    {
        EVENT_CHECKOUT_COMPLETED,
        EVENT_PAYMENT_FAILED,
        EVENT_PAYMENT_RECOVERED,
        EVENT_SUBSCRIPTION_CANCELED,
        EVENT_SUBSCRIPTION_EXPIRED,
        EVENT_SUBSCRIPTION_ACTIVE,
        EVENT_SUBSCRIPTION_TRIALING,
        EVENT_SUBSCRIPTION_PAST_DUE,
    }
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CheckoutSession:
    checkout_id: str
    account_id: str
    target_plan_code: str
    status: str
    provider: str
    checkout_url: Optional[str] = None

    def to_public_dict(self) -> dict[str, Any]:
        # Member-facing: opaque checkout id + target plan + status + the hosted
        # checkout URL to redirect to. No provider secrets, no customer/
        # subscription internal ids.
        return {
            "checkout_id": self.checkout_id,
            "target_plan_code": self.target_plan_code,
            "status": self.status,
            "provider": self.provider,
            "checkout_url": self.checkout_url,
        }


@dataclass(frozen=True)
class BillingPortalSession:
    """A provider-hosted billing/customer portal session (member-safe)."""

    portal_id: str
    provider: str
    portal_url: Optional[str] = None

    def to_public_dict(self) -> dict[str, Any]:
        return {"portal_id": self.portal_id, "provider": self.provider, "portal_url": self.portal_url}


@dataclass(frozen=True)
class CancellationResult:
    """Provider-neutral outcome of a cancellation request. The authoritative
    subscription state still follows a verified provider webhook; this only
    records that a cancellation was requested (e.g. at period end)."""

    provider: str
    status: str  # e.g. "cancellation_requested"
    cancel_at_period_end: bool = True
    provider_subscription_id: Optional[str] = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "cancel_at_period_end": self.cancel_at_period_end,
        }


@dataclass(frozen=True)
class ProviderSubscriptionReference:
    provider: str
    provider_customer_id: Optional[str]
    provider_subscription_id: Optional[str]


@dataclass(frozen=True)
class ProviderEvent:
    """A normalized, provider-neutral lifecycle event."""

    provider: str
    provider_event_id: str
    event_type: str
    account_id: Optional[str] = None
    provider_customer_id: Optional[str] = None
    provider_subscription_id: Optional[str] = None
    target_plan_code: Optional[str] = None
    effective_at: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.effective_at is None:
            object.__setattr__(self, "effective_at", _utcnow())

    @property
    def is_known_type(self) -> bool:
        return self.event_type in KNOWN_EVENT_TYPES


class PaymentProvider(Protocol):
    name: str

    def create_checkout_session(self, *, account_id: str, plan_code: str) -> CheckoutSession: ...

    def request_subscription_cancellation(
        self, *, account_id: str, provider_subscription_id: Optional[str]
    ) -> CancellationResult: ...

    def create_billing_portal_session(
        self, *, account_id: str, provider_customer_id: Optional[str]
    ) -> BillingPortalSession: ...

    def normalize_event(self, raw: Any) -> Optional["ProviderEvent"]: ...
