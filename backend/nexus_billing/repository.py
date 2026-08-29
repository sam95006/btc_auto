"""Persistence for BILLING-1 subscriptions (PostgreSQL).

Backed by the additive ``nexus.subscriptions`` table. A missing row is not an
error: callers resolve it to the safe default (free / inactive) via
``backend.nexus_billing.subscription.default_subscription``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from backend.nexus_persistence_pg.pool import PostgresPool
from backend.nexus_billing.plans import normalize_plan_code
from backend.nexus_billing.subscription import (
    STATUS_ACTIVE,
    STATUS_CANCELED,
    STATUS_EXPIRED,
    STATUS_INACTIVE,
    Subscription,
    assert_transition,
    is_valid_status,
)

_COLUMNS = (
    "subscription_id",
    "account_id",
    "plan_code",
    "status",
    "provider",
    "provider_customer_id",
    "provider_subscription_id",
    "started_at",
    "current_period_start",
    "current_period_end",
    "cancel_at",
    "canceled_at",
    "ended_at",
    "cancel_at_period_end",
    "created_at",
    "updated_at",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SubscriptionRepository:
    def __init__(self, pool: PostgresPool):
        self.pool = pool

    def _row_to_subscription(self, row: tuple[Any, ...]) -> Subscription:
        data = dict(zip(_COLUMNS, row))
        return Subscription(
            account_id=data["account_id"],
            plan_code=data["plan_code"],
            status=data["status"],
            provider=data["provider"],
            provider_customer_id=data["provider_customer_id"],
            provider_subscription_id=data["provider_subscription_id"],
            started_at=data["started_at"],
            current_period_start=data["current_period_start"],
            current_period_end=data["current_period_end"],
            cancel_at=data["cancel_at"],
            canceled_at=data["canceled_at"],
            ended_at=data["ended_at"],
            cancel_at_period_end=bool(data.get("cancel_at_period_end")),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    def get_by_account(self, account_id: str) -> Optional[Subscription]:
        rows = self.pool.fetchall(
            f"SELECT {', '.join(_COLUMNS)} FROM nexus.subscriptions WHERE account_id = %s LIMIT 1",
            (account_id,),
        )
        if not rows:
            return None
        return self._row_to_subscription(rows[0])

    def create_subscription(
        self,
        *,
        account_id: str,
        plan_code: str,
        status: str = STATUS_INACTIVE,
        provider: Optional[str] = None,
    ) -> Subscription:
        if not is_valid_status(status):
            raise ValueError("invalid_subscription_status")
        subscription_id = f"sub_{uuid.uuid4().hex[:16]}"
        plan = normalize_plan_code(plan_code)
        self.pool.execute(
            """
            INSERT INTO nexus.subscriptions (subscription_id, account_id, plan_code, status, provider)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (subscription_id, account_id, plan, status, provider),
        )
        created = self.get_by_account(account_id)
        assert created is not None
        return created

    def transition_status(self, account_id: str, to_status: str) -> Subscription:
        current = self.get_by_account(account_id)
        if current is None:
            raise ValueError("subscription_not_found")
        # Enforce the legal lifecycle; illegal transitions raise, never silently
        # succeed.
        assert_transition(current.status, to_status)
        self.pool.execute(
            "UPDATE nexus.subscriptions SET status = %s, updated_at = NOW() WHERE account_id = %s",
            (to_status, account_id),
        )
        updated = self.get_by_account(account_id)
        assert updated is not None
        return updated

    def ensure_subscription(self, account_id: str) -> Subscription:
        """Return the account's subscription row, creating a default inactive
        free row if none exists yet."""
        current = self.get_by_account(account_id)
        if current is not None:
            return current
        return self.create_subscription(account_id=account_id, plan_code="free", status=STATUS_INACTIVE)

    def apply_provider_transition(
        self,
        account_id: str,
        to_status: str,
        *,
        plan_code: Optional[str] = None,
        provider: Optional[str] = None,
        provider_customer_id: Optional[str] = None,
        provider_subscription_id: Optional[str] = None,
    ) -> Subscription:
        """Apply a provider-authoritative lifecycle transition with validation.

        The status change must be legal per the BILLING-1 state machine
        (illegal transitions raise, never silently succeed). Plan and provider
        metadata are set explicitly — there is no uncontrolled bulk update.
        Lifecycle timestamps are maintained for the meaningful transitions.
        """
        current = self.ensure_subscription(account_id)
        assert_transition(current.status, to_status)

        sets = ["status = %s", "updated_at = NOW()"]
        params: list[Any] = [to_status]
        if plan_code is not None:
            sets.append("plan_code = %s")
            params.append(normalize_plan_code(plan_code))
        if provider is not None:
            sets.append("provider = %s")
            params.append(provider)
        if provider_customer_id is not None:
            sets.append("provider_customer_id = %s")
            params.append(provider_customer_id)
        if provider_subscription_id is not None:
            sets.append("provider_subscription_id = %s")
            params.append(provider_subscription_id)
        if to_status == STATUS_ACTIVE:
            sets.append("started_at = COALESCE(started_at, NOW())")
            sets.append("current_period_start = NOW()")
            sets.append("current_period_end = NOW() + INTERVAL '30 days'")
            sets.append("canceled_at = NULL")
            sets.append("ended_at = NULL")
            # Reactivation clears any pending "cancel at period end".
            sets.append("cancel_at_period_end = FALSE")
        elif to_status == STATUS_CANCELED:
            sets.append("canceled_at = NOW()")
        elif to_status == STATUS_EXPIRED:
            sets.append("ended_at = NOW()")

        params.append(account_id)
        self.pool.execute(
            f"UPDATE nexus.subscriptions SET {', '.join(sets)} WHERE account_id = %s",
            tuple(params),
        )
        updated = self.get_by_account(account_id)
        assert updated is not None
        return updated

    def set_cancel_at_period_end(self, account_id: str, value: bool) -> None:
        self.pool.execute(
            "UPDATE nexus.subscriptions SET cancel_at_period_end = %s, updated_at = NOW() WHERE account_id = %s",
            (bool(value), account_id),
        )
