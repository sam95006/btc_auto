"""Durable billing-event idempotency ledger (PostgreSQL).

Idempotency is enforced by the ``UNIQUE (provider, provider_event_id)``
constraint on ``nexus.billing_events`` — not by process memory — so duplicate
provider deliveries (including concurrent ones across workers) are applied at
most once.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from backend.nexus_persistence_pg.pool import PostgresPool
from backend.nexus_billing.provider import ProviderEvent

STATUS_RECEIVED = "received"
STATUS_PROCESSED = "processed"
STATUS_REJECTED = "rejected"


class BillingEventRepository:
    def __init__(self, pool: PostgresPool):
        self.pool = pool

    def claim_event(self, event: ProviderEvent) -> tuple[str, bool]:
        """Atomically claim an event for processing.

        Returns (billing_event_id, is_new). ``is_new`` is False when the event
        (provider + provider_event_id) was already recorded, in which case the
        caller must treat processing as an idempotent no-op.
        """
        billing_event_id = f"be_{uuid.uuid4().hex[:16]}"
        rows = self.pool.fetchall(
            """
            INSERT INTO nexus.billing_events (
                billing_event_id, provider, provider_event_id, event_type,
                account_id, provider_customer_id, provider_subscription_id,
                target_plan_code, processing_status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (provider, provider_event_id) DO NOTHING
            RETURNING billing_event_id
            """,
            (
                billing_event_id,
                event.provider,
                event.provider_event_id,
                event.event_type,
                event.account_id,
                event.provider_customer_id,
                event.provider_subscription_id,
                event.target_plan_code,
                STATUS_RECEIVED,
            ),
        )
        if rows:
            return rows[0][0], True
        existing = self.get_by_provider_event(event.provider, event.provider_event_id)
        return (existing["billing_event_id"] if existing else billing_event_id), False

    def mark_processed(self, billing_event_id: str) -> None:
        self.pool.execute(
            "UPDATE nexus.billing_events SET processing_status = %s, processed_at = NOW() WHERE billing_event_id = %s",
            (STATUS_PROCESSED, billing_event_id),
        )

    def mark_rejected(self, billing_event_id: str, error_class: str) -> None:
        self.pool.execute(
            """
            UPDATE nexus.billing_events
            SET processing_status = %s, error_class = %s, processed_at = NOW()
            WHERE billing_event_id = %s
            """,
            (STATUS_REJECTED, error_class, billing_event_id),
        )

    def get_by_provider_event(self, provider: str, provider_event_id: str) -> Optional[dict[str, Any]]:
        rows = self.pool.fetchall(
            """
            SELECT billing_event_id, processing_status, event_type
            FROM nexus.billing_events
            WHERE provider = %s AND provider_event_id = %s
            LIMIT 1
            """,
            (provider, provider_event_id),
        )
        if not rows:
            return None
        return {"billing_event_id": rows[0][0], "processing_status": rows[0][1], "event_type": rows[0][2]}
