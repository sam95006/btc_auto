"""NexusDomainEvent bus — append-only, idempotency-keyed, dead-letter queue.

Events MUST NOT trigger real trading. Research-only.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

# ── Event type constants ────────────────────────────────────────────────────
MARKET_SNAPSHOT_UPDATED = "MARKET_SNAPSHOT_UPDATED"
CANDIDATE_APPEARED = "CANDIDATE_APPEARED"
CANDIDATE_UPDATED = "CANDIDATE_UPDATED"
CANDIDATE_SCORED = "CANDIDATE_SCORED"
CANDIDATE_CONFIRMED = "CANDIDATE_CONFIRMED"
CANDIDATE_EXPIRED = "CANDIDATE_EXPIRED"
CANDIDATE_INVALIDATED = "CANDIDATE_INVALIDATED"
REVIEW_CASE_CREATED = "REVIEW_CASE_CREATED"
REVIEW_CASE_UPDATED = "REVIEW_CASE_UPDATED"
REVIEW_CASE_CLOSED = "REVIEW_CASE_CLOSED"
REVIEW_CASE_EXPIRED = "REVIEW_CASE_EXPIRED"
ROLE_ASSESSMENT_STARTED = "ROLE_ASSESSMENT_STARTED"
ROLE_ASSESSMENT_COMPLETED = "ROLE_ASSESSMENT_COMPLETED"
ROLE_ASSESSMENT_FAILED = "ROLE_ASSESSMENT_FAILED"
RESEARCH_DECISION_PRODUCED = "RESEARCH_DECISION_PRODUCED"
RESEARCH_DECISION_EXPIRED = "RESEARCH_DECISION_EXPIRED"
REVIEW_CYCLE_STARTED = "REVIEW_CYCLE_STARTED"
REVIEW_CYCLE_COMPLETED = "REVIEW_CYCLE_COMPLETED"
REVIEW_CYCLE_SKIPPED = "REVIEW_CYCLE_SKIPPED"
SIM_PLACEHOLDER_CREATED = "SIM_PLACEHOLDER_CREATED"
SIM_PLACEHOLDER_UPDATED = "SIM_PLACEHOLDER_UPDATED"
REFLECTION_TRIGGERED = "REFLECTION_TRIGGERED"
REFLECTION_COMPLETED = "REFLECTION_COMPLETED"
PATCH_PROPOSED = "PATCH_PROPOSED"
PATCH_APPLIED = "PATCH_APPLIED"
SUPERVISOR_STARTED = "SUPERVISOR_STARTED"
SUPERVISOR_JOB_REGISTERED = "SUPERVISOR_JOB_REGISTERED"
SUPERVISOR_JOB_COMPLETED = "SUPERVISOR_JOB_COMPLETED"
SUPERVISOR_JOB_FAILED = "SUPERVISOR_JOB_FAILED"
SUPERVISOR_CIRCUIT_OPEN = "SUPERVISOR_CIRCUIT_OPEN"
SCANNER_SNAPSHOT_INGESTED = "SCANNER_SNAPSHOT_INGESTED"

_KNOWN_TYPES = {
    MARKET_SNAPSHOT_UPDATED, CANDIDATE_APPEARED, CANDIDATE_UPDATED, CANDIDATE_SCORED,
    CANDIDATE_CONFIRMED, CANDIDATE_EXPIRED, CANDIDATE_INVALIDATED,
    REVIEW_CASE_CREATED, REVIEW_CASE_UPDATED, REVIEW_CASE_CLOSED, REVIEW_CASE_EXPIRED,
    ROLE_ASSESSMENT_STARTED, ROLE_ASSESSMENT_COMPLETED, ROLE_ASSESSMENT_FAILED,
    RESEARCH_DECISION_PRODUCED, RESEARCH_DECISION_EXPIRED,
    REVIEW_CYCLE_STARTED, REVIEW_CYCLE_COMPLETED, REVIEW_CYCLE_SKIPPED,
    SIM_PLACEHOLDER_CREATED, SIM_PLACEHOLDER_UPDATED,
    REFLECTION_TRIGGERED, REFLECTION_COMPLETED,
    PATCH_PROPOSED, PATCH_APPLIED,
    SUPERVISOR_STARTED, SUPERVISOR_JOB_REGISTERED, SUPERVISOR_JOB_COMPLETED,
    SUPERVISOR_JOB_FAILED, SUPERVISOR_CIRCUIT_OPEN,
    SCANNER_SNAPSHOT_INGESTED,
}

_DLQ_CAPACITY = 200
_EVENT_LOG_CAPACITY = 2000


class NexusDomainEventBus:
    """Append-only event bus with idempotency key deduplication."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: deque[dict[str, Any]] = deque(maxlen=_EVENT_LOG_CAPACITY)
        self._idempotency_seen: dict[str, int] = {}  # key -> ts
        self._dlq: deque[dict[str, Any]] = deque(maxlen=_DLQ_CAPACITY)
        self._total_published = 0
        self._total_deduped = 0
        self._total_dlq = 0

    def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> str | None:
        """Publish an event. Returns event_id or None if deduped."""
        if event_type not in _KNOWN_TYPES:
            logger.warning("[events] unknown event type %r — sending to DLQ", event_type)
            self._send_to_dlq(event_type, payload, reason="unknown_type")
            return None

        with self._lock:
            if idempotency_key and idempotency_key in self._idempotency_seen:
                self._total_deduped += 1
                return None

            event_id = str(uuid.uuid4())
            now = int(time.time() * 1000)
            event: dict[str, Any] = {
                "eventId": event_id,
                "eventType": event_type,
                "correlationId": correlation_id or event_id,
                "causationId": causation_id,
                "idempotencyKey": idempotency_key,
                "publishedAt": now,
                "researchOnly": True,
                "payload": payload,
            }
            self._events.append(event)
            if idempotency_key:
                self._idempotency_seen[idempotency_key] = now
            self._total_published += 1
            return event_id

    def _send_to_dlq(self, event_type: str, payload: dict[str, Any], reason: str) -> None:
        with self._lock:
            self._dlq.append({
                "eventType": event_type,
                "reason": reason,
                "payload": payload,
                "ts": int(time.time() * 1000),
            })
            self._total_dlq += 1

    def recent(self, limit: int = 100, event_type: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._events)
        if event_type:
            events = [e for e in events if e["eventType"] == event_type]
        return events[-limit:]

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "researchOnly": True,
                "totalPublished": self._total_published,
                "totalDeduped": self._total_deduped,
                "totalDlq": self._total_dlq,
                "recentCount": len(self._events),
                "dlqCount": len(self._dlq),
                "dlqCapacity": _DLQ_CAPACITY,
                "eventLogCapacity": _EVENT_LOG_CAPACITY,
                "generatedAt": int(time.time() * 1000),
            }


_BUS: NexusDomainEventBus | None = None
_BUS_LOCK = threading.Lock()


def get_event_bus() -> NexusDomainEventBus:
    global _BUS
    with _BUS_LOCK:
        if _BUS is None:
            _BUS = NexusDomainEventBus()
        return _BUS


def publish_event(
    event_type: str,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> str | None:
    return get_event_bus().publish(
        event_type, payload,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
