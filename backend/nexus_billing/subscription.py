"""Subscription lifecycle model for BILLING-1.

The subscription state is a first-class lifecycle, never reduced to a boolean
``paid`` flag. Illegal transitions raise rather than silently succeeding. No
external payment provider is involved at this stage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from backend.nexus_billing.plans import DEFAULT_PLAN_CODE, normalize_plan_code

# Subscription lifecycle states.
STATUS_INACTIVE = "inactive"
STATUS_TRIALING = "trialing"
STATUS_ACTIVE = "active"
STATUS_PAST_DUE = "past_due"
STATUS_CANCELED = "canceled"
STATUS_EXPIRED = "expired"

CANONICAL_STATUSES: tuple[str, ...] = (
    STATUS_INACTIVE,
    STATUS_TRIALING,
    STATUS_ACTIVE,
    STATUS_PAST_DUE,
    STATUS_CANCELED,
    STATUS_EXPIRED,
)

# States in which a member is considered to hold a live (paying/trial) plan.
LIVE_STATUSES: frozenset[str] = frozenset({STATUS_TRIALING, STATUS_ACTIVE})

# Legal state transitions. Anything not listed is rejected.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_INACTIVE: frozenset({STATUS_TRIALING, STATUS_ACTIVE}),
    STATUS_TRIALING: frozenset({STATUS_ACTIVE, STATUS_CANCELED, STATUS_EXPIRED}),
    STATUS_ACTIVE: frozenset({STATUS_PAST_DUE, STATUS_CANCELED, STATUS_EXPIRED}),
    STATUS_PAST_DUE: frozenset({STATUS_ACTIVE, STATUS_CANCELED, STATUS_EXPIRED}),
    STATUS_CANCELED: frozenset({STATUS_EXPIRED}),
    STATUS_EXPIRED: frozenset(),  # terminal
}


class InvalidSubscriptionTransition(ValueError):
    """Raised when an illegal subscription state transition is attempted."""


def is_valid_status(status: Optional[str]) -> bool:
    return status in CANONICAL_STATUSES


def can_transition(from_status: str, to_status: str) -> bool:
    if not is_valid_status(from_status) or not is_valid_status(to_status):
        return False
    return to_status in ALLOWED_TRANSITIONS.get(from_status, frozenset())


def assert_transition(from_status: str, to_status: str) -> None:
    if not can_transition(from_status, to_status):
        raise InvalidSubscriptionTransition(f"{from_status}->{to_status}")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else None


@dataclass
class Subscription:
    account_id: str
    plan_code: str = DEFAULT_PLAN_CODE
    status: str = STATUS_INACTIVE
    provider: Optional[str] = None
    provider_customer_id: Optional[str] = None
    provider_subscription_id: Optional[str] = None
    started_at: Optional[datetime] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: Optional[datetime] = field(default=None)
    updated_at: Optional[datetime] = field(default=None)

    def __post_init__(self) -> None:
        # Never let an unknown plan/status silently grant a paid state.
        self.plan_code = normalize_plan_code(self.plan_code)
        if not is_valid_status(self.status):
            self.status = STATUS_INACTIVE

    @property
    def is_live(self) -> bool:
        return self.status in LIVE_STATUSES

    def transition_to(self, to_status: str) -> None:
        assert_transition(self.status, to_status)
        self.status = to_status

    def to_public_dict(self) -> dict[str, Any]:
        """Member-facing serialization. Intentionally excludes payment-provider
        internal identifiers (``provider``, ``provider_customer_id``,
        ``provider_subscription_id``) — the normal member frontend has no need
        for them and they must not leak through the member API."""
        return {
            "account_id": self.account_id,
            "plan_code": self.plan_code,
            "status": self.status,
            "is_live": self.is_live,
            "started_at": _iso(self.started_at),
            "current_period_start": _iso(self.current_period_start),
            "current_period_end": _iso(self.current_period_end),
            "cancel_at": _iso(self.cancel_at),
            "canceled_at": _iso(self.canceled_at),
            "ended_at": _iso(self.ended_at),
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }

    def to_internal_dict(self) -> dict[str, Any]:
        """Internal/operator serialization retaining provider identifiers, for
        later BILLING stages. Never returned by the member-facing API."""
        data = self.to_public_dict()
        data.update(
            {
                "provider": self.provider,
                "provider_customer_id": self.provider_customer_id,
                "provider_subscription_id": self.provider_subscription_id,
            }
        )
        return data


def default_subscription(account_id: str) -> Subscription:
    """The safe default for a member with no subscription row: the free plan in
    the inactive state. This is what every ambiguous/missing case resolves to,
    so a paid plan is never granted by accident."""
    return Subscription(account_id=account_id, plan_code=DEFAULT_PLAN_CODE, status=STATUS_INACTIVE)
