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
# Phase 6 Gate C — paper runtime events
PAPER_POSITION_EXITED = "paper.position.exited"
PAPER_CYCLE_COMPLETED = "paper.cycle.completed"
PAPER_GUARD_BLOCKED = "paper.guard.blocked"
# Phase 6.1 — persistence validation (research-only; must be registered to avoid DLQ)
PERSISTENCE_VALIDATION_PACK_CREATED = "PERSISTENCE_VALIDATION_PACK_CREATED"

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
    PAPER_POSITION_EXITED, PAPER_CYCLE_COMPLETED, PAPER_GUARD_BLOCKED,
    PERSISTENCE_VALIDATION_PACK_CREATED,
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
            # Durable append for restart recovery / idempotency evidence.
            try:
                from backend.nexus_research.storage import get_research_store

                get_research_store().append(
                    "domain_events",
                    {
                        "event_id": event_id,
                        "eventId": event_id,
                        "event_type": event_type,
                        "eventType": event_type,
                        "tag": "research",
                        "idempotencyKey": idempotency_key,
                        "correlationId": event["correlationId"],
                        "payload": payload,
                        "researchOnly": True,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("[events] failed to persist domain event: %s", exc)
            return event_id
    def _send_to_dlq(self, event_type: str, payload: dict[str, Any], reason: str) -> None:
        import hashlib
        import json as _json

        payload_hash = hashlib.sha256(
            _json.dumps(payload or {}, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        # Stable idempotency so restart / retry does not duplicate DLQ rows.
        letter_id = f"dlq:{event_type}:{payload_hash}:{reason}"
        now = int(time.time() * 1000)
        entry = {
            "letter_id": letter_id,
            "letterId": letter_id,
            "eventId": letter_id,
            "eventType": event_type,
            "failureReason": reason,
            "reason": reason,
            "source": "domain_event_bus",
            "payloadHash": payload_hash,
            "payload": payload,
            "occurredAt": now,
            "failedAt": now,
            "retryCount": 0,
            "status": "OPEN",
            "correlationId": (payload or {}).get("correlationId") if isinstance(payload, dict) else None,
            "schemaVersion": 1,
            "ts": now,
            "researchOnly": True,
            # Preserve V1 root-cause note — never delete historical evidence.
            "note": "durable_dlq_v1",
        }
        with self._lock:
            self._dlq.append(entry)
            self._total_dlq += 1
        try:
            from backend.nexus_research.storage import get_research_store

            get_research_store().append("dead_letters", entry)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[events] failed to persist DLQ entry: %s", exc)
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
