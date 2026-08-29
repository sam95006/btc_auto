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

from backend.nexus_billing.event_repository import (
    DECISION_TERMINAL_PROCESSED,
    DECISION_TERMINAL_REJECTED,
)
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
    CheckoutSession,
    PaymentProvider,
    ProviderEvent,
)
from backend.nexus_billing.subscription import (
    STATUS_ACTIVE,
    STATUS_CANCELED,
    STATUS_EXPIRED,
    STATUS_PAST_DUE,
    STATUS_TRIALING,
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
    EVENT_SUBSCRIPTION_ACTIVE: STATUS_ACTIVE,
    EVENT_SUBSCRIPTION_TRIALING: STATUS_TRIALING,
    EVENT_SUBSCRIPTION_PAST_DUE: STATUS_PAST_DUE,
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
        # Free is not a checkout; Enterprise is not self-service (contract sales).
        if plan is None or plan.code in (PLAN_FREE, PLAN_ENTERPRISE):
            raise BillingError("invalid_checkout_plan")
        logger.info("billing.checkout_initiated", extra={"account_id": account_id, "plan_code": plan.code})
        return self._provider.create_checkout_session(account_id=account_id, plan_code=plan.code)

    # ----- cancellation (provider-neutral; authoritative state via webhook) -----
    def request_cancellation(self, *, account_id: str) -> dict[str, Any]:
        subscription = self._subs.get_by_account(account_id)
        if subscription is None or subscription.status not in ("trialing", "active", "past_due"):
            # Nothing cancelable; safe no-op response (never mutates).
            return {"status": "no_active_subscription", "cancel_at_period_end": False}
        result = self._provider.request_subscription_cancellation(
            account_id=account_id, provider_subscription_id=subscription.provider_subscription_id
        )
        # Record ONLY the "cancellation requested" intent. We do NOT fake the
        # lifecycle transition here — the authoritative canceled/expired state
        # arrives later as a verified provider webhook event.
        if hasattr(self._subs, "set_cancel_at_period_end"):
            self._subs.set_cancel_at_period_end(account_id, True)
        logger.info("billing.cancellation_requested", extra={"account_id": account_id})
        return {"status": result.status, "cancel_at_period_end": result.cancel_at_period_end}

    def create_billing_portal(self, *, account_id: str):
        subscription = self._subs.get_by_account(account_id)
        customer = subscription.provider_customer_id if subscription else None
        return self._provider.create_billing_portal_session(
            account_id=account_id, provider_customer_id=customer
        )

    # ----- event processing (idempotent + crash-recovery + state-safe) -----
    def process_provider_event(self, event: ProviderEvent) -> dict[str, Any]:
        # Malformed events cannot even be claimed (no stable identity).
        if not event.provider or not event.provider_event_id or not event.event_type:
            logger.warning("billing.event_rejected", extra={"reason": "malformed_event"})
            return {"status": "rejected", "reason": "malformed_event"}

        claim = self._events.begin_processing(event)
        if claim.decision == DECISION_TERMINAL_PROCESSED:
            logger.info("billing.event_already_processed", extra={"provider": event.provider})
            return {"status": "already_processed", "billing_event_id": claim.billing_event_id}
        if claim.decision == DECISION_TERMINAL_REJECTED:
            return {"status": "already_rejected", "billing_event_id": claim.billing_event_id}

        bid = claim.billing_event_id

        # Permanent rejections (deterministic; provider retry cannot fix these).
        rejection = self._reject_reason(event)
        if rejection is not None:
            self._events.mark_rejected(bid, rejection)
            logger.warning("billing.event_rejected", extra={"reason": rejection})
            return {"status": "rejected", "reason": rejection, "billing_event_id": bid}

        target_status = _EVENT_TARGET_STATUS[event.event_type]
        try:
            current = self._subs.ensure_subscription(event.account_id)

            # Convergence: recovers "crashed after mutation, before marking
            # processed" and concurrent duplicate delivery. If the subscription
            # already holds the event's target state (and metadata agrees),
            # mark the event processed instead of falsely rejecting active->active.
            if current.status == target_status and self._converges(current, event):
                self._events.mark_processed(bid)
                return {
                    "status": "processed",
                    "converged": True,
                    "billing_event_id": bid,
                    "subscription_status": current.status,
                    "effective_plan_code": current.plan_code,
                }

            if not can_transition(current.status, target_status):
                # Genuinely illegal/out-of-order and not convergent: fail closed,
                # deterministically, without mutating or granting paid access.
                self._events.mark_rejected(bid, "illegal_transition")
                logger.warning(
                    "billing.event_rejected",
                    extra={"reason": "illegal_transition", "from": current.status, "to": target_status},
                )
                return {
                    "status": "rejected",
                    "reason": "illegal_transition",
                    "from": current.status,
                    "to": target_status,
                    "billing_event_id": bid,
                }

            # Set the plan whenever the event carries one (activation-style
            # events); lifecycle-only events (failure/cancel/expire) carry none.
            plan_code = event.target_plan_code
            updated = self._subs.apply_provider_transition(
                event.account_id,
                target_status,
                plan_code=plan_code,
                provider=event.provider,
                provider_customer_id=event.provider_customer_id,
                provider_subscription_id=event.provider_subscription_id,
            )
            self._events.mark_processed(bid)
            logger.info(
                "billing.subscription_transitioned",
                extra={"account_id": event.account_id, "to": target_status, "plan_code": updated.plan_code},
            )
            return {
                "status": "processed",
                "billing_event_id": bid,
                "subscription_status": updated.status,
                "effective_plan_code": updated.plan_code,
            }
        except Exception as exc:  # noqa: BLE001 - class name only, never message
            # Transient failure: leave the event non-terminal so a provider
            # retry can recover it. Never mark it permanently processed.
            self._events.record_transient_error(bid, type(exc).__name__)
            logger.warning("billing.event_transient_error", extra={"error_class": type(exc).__name__})
            return {"status": "error", "retryable": True, "error_class": type(exc).__name__, "billing_event_id": bid}

    def _converges(self, current: Any, event: ProviderEvent) -> bool:
        """True when the subscription already reflects this event's intended
        outcome, so re-delivery is a safe no-op rather than an illegal reject."""
        if event.target_plan_code:
            plan = get_plan(event.target_plan_code)
            if plan is None or current.plan_code != plan.code:
                return False
        if (
            event.provider_subscription_id
            and current.provider_subscription_id
            and current.provider_subscription_id != event.provider_subscription_id
        ):
            return False
        return True

    def _reject_reason(self, event: ProviderEvent) -> Optional[str]:
        if event.provider != self._provider.name:
            return "provider_mismatch"
        if not event.is_known_type:
            return "unsupported_event_type"
        if not event.account_id:
            return "missing_account"
        # Checkout must name a plan; any event that carries a plan must name a
        # known, paid one. The server is authoritative for plan identity.
        if event.event_type == EVENT_CHECKOUT_COMPLETED and not event.target_plan_code:
            return "unknown_plan"
        if event.target_plan_code:
            plan = get_plan(event.target_plan_code)
            if plan is None or plan.code == PLAN_FREE:
                return "unknown_plan"
        return None
