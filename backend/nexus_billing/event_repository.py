"""Durable billing-event idempotency + crash-recovery ledger (PostgreSQL).

Idempotency is enforced by ``UNIQUE (provider, provider_event_id)`` on
``nexus.billing_events`` — not process memory — so duplicate provider deliveries
(including concurrent ones) are recorded once.

Crash recovery: only ``processed`` and ``rejected`` are terminal states. A row
left in ``received``/``processing`` (e.g. a worker crashed before it finished)
is NOT treated as done; the next delivery re-attempts it. Combined with a
convergent, idempotent subscription mutation, this yields at-most-once *effect*
while still recovering from crashes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from backend.nexus_persistence_pg.pool import PostgresPool
from backend.nexus_billing.provider import ProviderEvent

STATUS_RECEIVED = "received"
STATUS_PROCESSING = "processing"
STATUS_PROCESSED = "processed"
STATUS_REJECTED = "rejected"

TERMINAL_STATUSES = frozenset({STATUS_PROCESSED, STATUS_REJECTED})

# begin_processing decisions
DECISION_NEW = "new"
DECISION_RETRY = "retry"
DECISION_TERMINAL_PROCESSED = "terminal_processed"
DECISION_TERMINAL_REJECTED = "terminal_rejected"


@dataclass(frozen=True)
class ProcessingClaim:
    billing_event_id: str
    decision: str

    @property
    def should_process(self) -> bool:
        return self.decision in (DECISION_NEW, DECISION_RETRY)


class BillingEventRepository:
    def __init__(self, pool: PostgresPool):
        self.pool = pool

    def begin_processing(self, event: ProviderEvent) -> ProcessingClaim:
        """Claim an event for processing, recovering crashed attempts.

        - New event -> inserted as 'processing', decision NEW.
        - Existing terminal (processed/rejected) -> skip (idempotent).
        - Existing non-terminal (received/processing) -> re-attempt, decision RETRY
          (a previous worker crashed before reaching a terminal state).
        """
        billing_event_id = f"be_{uuid.uuid4().hex[:16]}"
        rows = self.pool.fetchall(
            """
            INSERT INTO nexus.billing_events (
                billing_event_id, provider, provider_event_id, event_type,
                account_id, provider_customer_id, provider_subscription_id,
                target_plan_code, processing_status, processing_started_at,
                processing_attempts, last_attempt_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), 1, NOW())
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
                STATUS_PROCESSING,
            ),
        )
        if rows:
            return ProcessingClaim(rows[0][0], DECISION_NEW)

        existing = self.get_by_provider_event(event.provider, event.provider_event_id)
        if existing is None:
            # Extremely unlikely race; treat as new attempt id.
            return ProcessingClaim(billing_event_id, DECISION_RETRY)
        status = existing["processing_status"]
        eid = existing["billing_event_id"]
        if status == STATUS_PROCESSED:
            return ProcessingClaim(eid, DECISION_TERMINAL_PROCESSED)
        if status == STATUS_REJECTED:
            return ProcessingClaim(eid, DECISION_TERMINAL_REJECTED)
        # received/processing -> a prior attempt did not reach a terminal state.
        self.pool.execute(
            """
            UPDATE nexus.billing_events
            SET processing_status = %s,
                processing_attempts = processing_attempts + 1,
                last_attempt_at = NOW()
            WHERE billing_event_id = %s
            """,
            (STATUS_PROCESSING, eid),
        )
        return ProcessingClaim(eid, DECISION_RETRY)

    def mark_processed(self, billing_event_id: str) -> None:
        self.pool.execute(
            "UPDATE nexus.billing_events SET processing_status = %s, processed_at = NOW() WHERE billing_event_id = %s",
            (STATUS_PROCESSED, billing_event_id),
        )

    def mark_rejected(self, billing_event_id: str, error_class: str) -> None:
        self.pool.execute(
            """
            UPDATE nexus.billing_events
            SET processing_status = %s, error_class = %s, processed_at = NOW(), last_error_at = NOW()
            WHERE billing_event_id = %s
            """,
            (STATUS_REJECTED, error_class, billing_event_id),
        )

    def record_transient_error(self, billing_event_id: str, error_class: str) -> None:
        """Record a retryable failure WITHOUT reaching a terminal state, so the
        provider's retry can recover it."""
        self.pool.execute(
            """
            UPDATE nexus.billing_events
            SET processing_status = %s, error_class = %s, last_error_at = NOW()
            WHERE billing_event_id = %s
            """,
            (STATUS_RECEIVED, error_class, billing_event_id),
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
