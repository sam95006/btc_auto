"""Stripe adapter for the provider-neutral Billing core (BILLING-4).

SANDBOX / TEST MODE ONLY. A live secret key (``sk_live_``/``rk_live_``) is
rejected outright — there is no fallback and no "try anyway". Billing Core never
imports this module or parses Stripe payloads; all Stripe specifics live here.

Offline-safe: config validation, webhook signature verification, event
normalization, and checkout-parameter building require NO Stripe SDK and no
network. Only the actual hosted-checkout creation calls the Stripe API (lazy
import), which is what the sandbox-runtime E2E needs.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any, Optional

from backend.nexus_billing.plans import PLAN_ENTERPRISE, PLAN_FREE, get_plan
from backend.nexus_billing.provider import (
    EVENT_CHECKOUT_COMPLETED,
    EVENT_PAYMENT_FAILED,
    EVENT_PAYMENT_RECOVERED,
    EVENT_SUBSCRIPTION_ACTIVE,
    EVENT_SUBSCRIPTION_CANCELED,
    EVENT_SUBSCRIPTION_EXPIRED,
    EVENT_SUBSCRIPTION_PAST_DUE,
    EVENT_SUBSCRIPTION_TRIALING,
    BillingPortalSession,
    CancellationResult,
    CheckoutSession,
    ProviderEvent,
)

STRIPE_PROVIDER_NAME = "stripe"
_DEFAULT_SIGNATURE_TOLERANCE_SECONDS = 300

# Plans that support self-service checkout. Enterprise is intentionally NOT
# self-service by default (contract/commercial handling belongs elsewhere).
_SELF_SERVICE_EXCLUDED = frozenset({PLAN_FREE, PLAN_ENTERPRISE})


class StripeConfigError(ValueError):
    """Raised when the Stripe configuration is unsafe or incomplete."""


def is_live_secret_key(key: str) -> bool:
    key = (key or "").strip()
    return key.startswith(("sk_live_", "rk_live_")) or "pk_live_" in key


def is_test_secret_key(key: str) -> bool:
    return (key or "").strip().startswith(("sk_test_", "rk_test_"))


@dataclass(frozen=True)
class StripeConfig:
    secret_key: str
    webhook_secret: str
    success_url: str
    cancel_url: str
    price_by_plan: dict[str, str]
    signature_tolerance_seconds: int = _DEFAULT_SIGNATURE_TOLERANCE_SECONDS

    def validate(self) -> None:
        if is_live_secret_key(self.secret_key):
            raise StripeConfigError("live_stripe_key_forbidden")
        if not is_test_secret_key(self.secret_key):
            raise StripeConfigError("stripe_secret_key_must_be_test")
        if not self.webhook_secret:
            raise StripeConfigError("missing_webhook_secret")
        if not self.success_url or not self.cancel_url:
            raise StripeConfigError("missing_redirect_urls")
        if not self.price_by_plan:
            raise StripeConfigError("missing_price_map")

    @classmethod
    def from_env(cls, env: dict[str, str]) -> Optional["StripeConfig"]:
        secret_key = (env.get("STRIPE_SECRET_KEY") or "").strip()
        webhook_secret = (env.get("STRIPE_WEBHOOK_SECRET") or "").strip()
        success_url = (env.get("STRIPE_SUCCESS_URL") or "").strip()
        cancel_url = (env.get("STRIPE_CANCEL_URL") or "").strip()
        price_by_plan: dict[str, str] = {}
        for plan_code, key in (
            ("starter", "STRIPE_PRICE_STARTER"),
            ("pro", "STRIPE_PRICE_PRO"),
            ("advanced", "STRIPE_PRICE_ADVANCED"),
        ):
            price = (env.get(key) or "").strip()
            if price:
                price_by_plan[plan_code] = price
        if not secret_key or not webhook_secret or not success_url or not cancel_url or not price_by_plan:
            return None
        return cls(
            secret_key=secret_key,
            webhook_secret=webhook_secret,
            success_url=success_url,
            cancel_url=cancel_url,
            price_by_plan=price_by_plan,
        )


def verify_stripe_signature(
    payload: bytes, sig_header: str, secret: str, *, tolerance: int = _DEFAULT_SIGNATURE_TOLERANCE_SECONDS,
    now: Optional[int] = None,
) -> bool:
    """Verify a Stripe webhook signature against the RAW request body.

    Implements Stripe's scheme (HMAC-SHA256 over ``"{t}.{payload}"``) without the
    SDK. Returns False on any missing/invalid/expired signature.
    """
    if not payload or not sig_header or not secret:
        return False
    parts = {}
    for item in sig_header.split(","):
        if "=" in item:
            k, _, v = item.partition("=")
            parts.setdefault(k.strip(), []).append(v.strip())
    timestamps = parts.get("t") or []
    signatures = parts.get("v1") or []
    if not timestamps or not signatures:
        return False
    try:
        ts = int(timestamps[0])
    except ValueError:
        return False
    current = int(time.time()) if now is None else int(now)
    if tolerance and abs(current - ts) > tolerance:
        return False
    signed_payload = f"{ts}.".encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in signatures)


def build_checkout_params(
    *, account_id: str, plan_code: str, price_id: str, success_url: str, cancel_url: str
) -> dict[str, Any]:
    """Pure builder for Stripe Checkout Session params (server-authoritative).

    The plan/account travel in metadata (on the session AND the resulting
    subscription) so later subscription/invoice events can be tied back to an
    internal account and plan. No sensitive data is placed in metadata.
    """
    metadata = {"account_id": account_id, "plan_code": plan_code}
    return {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": account_id,
        "metadata": dict(metadata),
        "subscription_data": {"metadata": dict(metadata)},
    }


def map_stripe_subscription_status(stripe_status: Optional[str]) -> Optional[str]:
    """Map a Stripe subscription status to an internal normalized event type.

    Unknown statuses return None (fail closed — never auto-active)."""
    mapping = {
        "active": EVENT_SUBSCRIPTION_ACTIVE,
        "trialing": EVENT_SUBSCRIPTION_TRIALING,
        "past_due": EVENT_SUBSCRIPTION_PAST_DUE,
        "unpaid": EVENT_SUBSCRIPTION_PAST_DUE,
        "canceled": EVENT_SUBSCRIPTION_CANCELED,
        "incomplete_expired": EVENT_SUBSCRIPTION_EXPIRED,
    }
    return mapping.get((stripe_status or "").strip())


def _metadata(obj: dict[str, Any]) -> dict[str, Any]:
    md = obj.get("metadata")
    return md if isinstance(md, dict) else {}


def normalize_stripe_event(event: dict[str, Any]) -> Optional[ProviderEvent]:
    """Normalize a Stripe event dict into an internal ProviderEvent.

    Returns None for events that are safe to ignore (unknown type, or a known
    type carrying an unknown/unmapped status) — the webhook acknowledges those
    with 2xx without mutating state. Never trusts a browser redirect.
    """
    event_type = str(event.get("type") or "")
    provider_event_id = str(event.get("id") or "")
    data_object = ((event.get("data") or {}).get("object") or {})
    if not provider_event_id or not isinstance(data_object, dict):
        return None

    def _make(internal_type: str, *, plan_code: Optional[str], customer, subscription,
              cancel_at_period_end: Optional[bool] = None) -> ProviderEvent:
        return ProviderEvent(
            provider=STRIPE_PROVIDER_NAME,
            provider_event_id=provider_event_id,
            event_type=internal_type,
            account_id=account_id,
            provider_customer_id=str(customer) if customer else None,
            provider_subscription_id=str(subscription) if subscription else None,
            target_plan_code=plan_code,
            cancel_at_period_end=cancel_at_period_end,
        )

    if event_type == "checkout.session.completed":
        md = _metadata(data_object)
        account_id = md.get("account_id") or data_object.get("client_reference_id")
        return _make(
            EVENT_CHECKOUT_COMPLETED,
            plan_code=md.get("plan_code"),
            customer=data_object.get("customer"),
            subscription=data_object.get("subscription"),
        )

    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        md = _metadata(data_object)
        account_id = md.get("account_id")
        internal = map_stripe_subscription_status(data_object.get("status"))
        if internal is None:
            return None  # unknown status -> fail closed / ignore
        cape = data_object.get("cancel_at_period_end")
        return _make(
            internal,
            plan_code=md.get("plan_code") if internal in (EVENT_SUBSCRIPTION_ACTIVE, EVENT_SUBSCRIPTION_TRIALING) else None,
            customer=data_object.get("customer"),
            subscription=data_object.get("id"),
            cancel_at_period_end=bool(cape) if isinstance(cape, bool) else None,
        )

    if event_type == "customer.subscription.deleted":
        md = _metadata(data_object)
        account_id = md.get("account_id")
        return _make(EVENT_SUBSCRIPTION_CANCELED, plan_code=None,
                     customer=data_object.get("customer"), subscription=data_object.get("id"))

    if event_type == "invoice.paid":
        md = _metadata(data_object)
        account_id = md.get("account_id") or _metadata(data_object.get("subscription_details") or {}).get("account_id")
        return _make(EVENT_PAYMENT_RECOVERED, plan_code=None,
                     customer=data_object.get("customer"), subscription=data_object.get("subscription"))

    if event_type == "invoice.payment_failed":
        md = _metadata(data_object)
        account_id = md.get("account_id")
        return _make(EVENT_PAYMENT_FAILED, plan_code=None,
                     customer=data_object.get("customer"), subscription=data_object.get("subscription"))

    return None  # unknown/ignored event type


class StripePaymentProvider:
    """PaymentProvider adapter for Stripe (sandbox/test only)."""

    name = STRIPE_PROVIDER_NAME

    def __init__(self, config: StripeConfig) -> None:
        config.validate()  # rejects live keys / incomplete config
        self._config = config

    def price_for_plan(self, plan_code: str) -> Optional[str]:
        plan = get_plan(plan_code)
        if plan is None or plan.code in _SELF_SERVICE_EXCLUDED:
            return None
        return self._config.price_by_plan.get(plan.code)

    def create_checkout_session(self, *, account_id: str, plan_code: str) -> CheckoutSession:
        price_id = self.price_for_plan(plan_code)
        if price_id is None:
            raise StripeConfigError("plan_not_available_for_checkout")
        params = build_checkout_params(
            account_id=account_id,
            plan_code=get_plan(plan_code).code,  # type: ignore[union-attr]
            price_id=price_id,
            success_url=self._config.success_url,
            cancel_url=self._config.cancel_url,
        )
        # Lazy import: only the real hosted-checkout creation needs the SDK.
        try:
            import stripe  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise StripeConfigError("stripe_sdk_not_installed") from exc
        stripe.api_key = self._config.secret_key
        session = stripe.checkout.Session.create(**params)  # pragma: no cover - needs sandbox creds
        checkout_url = session.get("url")
        if not checkout_url:
            # Never hand the frontend a missing/malformed redirect to guess at.
            raise StripeConfigError("stripe_checkout_url_missing")
        return CheckoutSession(
            checkout_id=str(session.get("id")),
            account_id=account_id,
            target_plan_code=get_plan(plan_code).code,  # type: ignore[union-attr]
            status=str(session.get("status") or "open"),
            provider=self.name,
            checkout_url=str(checkout_url),
        )

    def request_subscription_cancellation(
        self, *, account_id: str, provider_subscription_id: Optional[str]
    ) -> CancellationResult:
        # Provider-authoritative cancellation at period end. Stripe remains the
        # source of truth: the resulting subscription lifecycle change arrives as
        # a verified webhook; we do not fake it locally.
        if not provider_subscription_id:
            return CancellationResult(provider=self.name, status="no_subscription", cancel_at_period_end=False)
        try:
            import stripe  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise StripeConfigError("stripe_sdk_not_installed") from exc
        stripe.api_key = self._config.secret_key
        stripe.Subscription.modify(  # pragma: no cover - needs sandbox creds
            provider_subscription_id, cancel_at_period_end=True
        )
        return CancellationResult(
            provider=self.name,
            status="cancellation_requested",
            cancel_at_period_end=True,
            provider_subscription_id=provider_subscription_id,
        )

    def create_billing_portal_session(
        self, *, account_id: str, provider_customer_id: Optional[str]
    ) -> BillingPortalSession:
        if not provider_customer_id:
            raise StripeConfigError("no_customer_for_portal")
        try:
            import stripe  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise StripeConfigError("stripe_sdk_not_installed") from exc
        stripe.api_key = self._config.secret_key
        portal = stripe.billing_portal.Session.create(  # pragma: no cover - needs sandbox creds
            customer=provider_customer_id, return_url=self._config.success_url
        )
        portal_id = portal.get("id")
        portal_url = portal.get("url")
        if not portal_id or not portal_url:
            # Never hand the frontend a "None"/empty portal to guess at.
            raise StripeConfigError("stripe_portal_url_missing")
        return BillingPortalSession(portal_id=str(portal_id), provider=self.name, portal_url=str(portal_url))

    def normalize_event(self, raw: Any) -> Optional[ProviderEvent]:
        if isinstance(raw, ProviderEvent):
            return raw
        if isinstance(raw, dict):
            return normalize_stripe_event(raw)
        raise ValueError("unsupported_raw_event")
