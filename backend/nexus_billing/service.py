"""Central Billing orchestration service for BILLING-3.

Coordinates the payment provider, the durable billing-event ledger, the
subscription repository, and the BILLING-1 subscription state machine. Routes
must not mutate subscriptions directly — all lifecycle logic lives here.

Entitlements are NOT computed here; they remain the responsibility of the
BILLING-2 resolver, which reads the subscription state this service maintains.

Trading firewall: nothing in this service enables or authorizes trading.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from backend.nexus_billing.plans import PLAN_FREE, get_plan
from backend.nexus_billing.provider import (
    EVENT_CHECKOUT_COMPLETED,
    EVENT_PAYMENT_FAILED,
    EVENT_PAYMENT_RECOVERED,
    EVENT_SUBSCRIPTION_CANCELED,
    EVENT_SUBSCRIPTION_EXPIRED,
    CheckoutSession,
    PaymentProvider,
    ProviderEvent,
)
from backend.nexus_billing.subscription import (
    STATUS_ACTIVE,
    STATUS_CANCELED,
    STATUS_EXPIRED,
    STATUS_PAST_DUE,
    can_transition,
)

logger = logging.getLogger("nexus.billing")

# Normalized event type -> target subscription status.
_EVENT_TARGET_STATUS: dict[str, str] = {
    EVENT_CHECKOUT_COMPLETED: STATUS_ACTIVE,
    EVENT_PAYMENT_FAILED: STATUS_PAST_DUE,
    EVENT_PAYMENT_RECOVERED: STATUS_ACTIVE,
    EVENT_SUBSCRIPTION_CANCELED: STATUS_CANCELED,
    EVENT_SUBSCRIPTION_EXPIRED: STATUS_EXPIRED,
}


class BillingError(ValueError):
    """Raised for invalid billing requests (e.g. unknown checkout plan)."""


class BillingService:
    def __init__(self, *, subscription_repo, event_repo, provider: PaymentProvider) -> None:
        self._subs = subscription_repo
        self._events = event_repo
        self._provider = provider

    # ----- checkout -----
    def start_checkout(self, *, account_id: str, plan_code: str) -> CheckoutSession:
        """Begin a checkout for a KNOWN, paid plan. Unknown or free plans are
        rejected here (checkout is an action, not a fail-safe read): an unknown
        requested plan must never be normalized to free and continue."""
        plan = get_plan(plan_code)
        if plan is None or plan.code == PLAN_FREE:
            raise BillingError("invalid_checkout_plan")
        logger.info("billing.checkout_initiated", extra={"account_id": account_id, "plan_code": plan.code})
        return self._provider.create_checkout_session(account_id=account_id, plan_code=plan.code)

    # ----- cancellation -----
    def request_cancellation(self, *, account_id: str) -> dict[str, Any]:
        subscription = self._subs.get_by_account(account_id)
        provider_subscription_id = subscription.provider_subscription_id if subscription else None
        event = self._provider.cancel_subscription(
            account_id=account_id, provider_subscription_id=provider_subscription_id
        )
        return self.process_provider_event(event)

    # ----- event processing (idempotent + state-machine safe) -----
    def process_provider_event(self, event: ProviderEvent) -> dict[str, Any]:
        # Malformed events cannot even be claimed (no stable identity).
        if not event.provider or not event.provider_event_id or not event.event_type:
            logger.warning("billing.event_rejected", extra={"reason": "malformed_event"})
            return {"status": "rejected", "reason": "malformed_event"}

        billing_event_id, is_new = self._events.claim_event(event)
        if not is_new:
            # Durable idempotency: a duplicate delivery is a no-op.
            logger.info(
                "billing.event_already_processed",
                extra={"provider": event.provider, "provider_event_id": event.provider_event_id},
            )
            return {"status": "already_processed", "billing_event_id": billing_event_id}

        rejection = self._reject_reason(event)
        if rejection is not None:
            self._events.mark_rejected(billing_event_id, rejection)
            logger.warning("billing.event_rejected", extra={"reason": rejection})
            return {"status": "rejected", "reason": rejection, "billing_event_id": billing_event_id}

        target_status = _EVENT_TARGET_STATUS[event.event_type]
        current = self._subs.ensure_subscription(event.account_id)
        if not can_transition(current.status, target_status):
            # Illegal lifecycle transition (e.g. out-of-order event). Fail closed:
            # never mutate, never grant paid access.
            self._events.mark_rejected(billing_event_id, "illegal_transition")
            logger.warning(
                "billing.event_rejected",
                extra={"reason": "illegal_transition", "from": current.status, "to": target_status},
            )
            return {
                "status": "rejected",
                "reason": "illegal_transition",
                "from": current.status,
                "to": target_status,
                "billing_event_id": billing_event_id,
            }

        plan_code = event.target_plan_code if event.event_type == EVENT_CHECKOUT_COMPLETED else None
        updated = self._subs.apply_provider_transition(
            event.account_id,
            target_status,
            plan_code=plan_code,
            provider=event.provider,
            provider_customer_id=event.provider_customer_id,
            provider_subscription_id=event.provider_subscription_id,
        )
        self._events.mark_processed(billing_event_id)
        logger.info(
            "billing.subscription_transitioned",
            extra={
                "account_id": event.account_id,
                "to": target_status,
                "plan_code": updated.plan_code,
            },
        )
        return {
            "status": "processed",
            "billing_event_id": billing_event_id,
            "subscription_status": updated.status,
            "effective_plan_code": updated.plan_code,
        }

    def _reject_reason(self, event: ProviderEvent) -> Optional[str]:
        if event.provider != self._provider.name:
            return "provider_mismatch"
        if not event.is_known_type:
            return "unsupported_event_type"
        if not event.account_id:
            return "missing_account"
        if event.event_type == EVENT_CHECKOUT_COMPLETED:
            plan = get_plan(event.target_plan_code)
            if plan is None or plan.code == PLAN_FREE:
                return "unknown_plan"
        return None
