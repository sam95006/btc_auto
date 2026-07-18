"""CandidateReviewCase manager for Phase 5 Gate B.

Triggers: TOP5_ENTRY, CONFIRMED, SCORE_CHANGE, MAJOR_ANOMALY,
          POSITION_RISK, SCHEDULED_REVIEW, MANUAL_RESEARCH.
Statuses: PENDING → IN_REVIEW → COMPLETED | EXPIRED | CANCELLED.
Dedup same candidate/direction/window. Cooldown per symbol.
Close on candidate invalidation.
All eligible deep-scan symbols; not BTC/ETH/SOL only.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any

from backend.nexus_research.domain_events import (
    REVIEW_CASE_CLOSED,
    REVIEW_CASE_CREATED,
    REVIEW_CASE_EXPIRED,
    REVIEW_CASE_UPDATED,
    SCANNER_SNAPSHOT_INGESTED,
    publish_event,
)
from backend.nexus_research.storage import get_research_store

logger = logging.getLogger(__name__)

# ── Trigger types ───────────────────────────────────────────────────────────
TRIGGER_TOP5_ENTRY = "TOP5_ENTRY"
TRIGGER_CONFIRMED = "CONFIRMED"
TRIGGER_SCORE_CHANGE = "SCORE_CHANGE"
TRIGGER_MAJOR_ANOMALY = "MAJOR_ANOMALY"
TRIGGER_POSITION_RISK = "POSITION_RISK"
TRIGGER_SCHEDULED_REVIEW = "SCHEDULED_REVIEW"
TRIGGER_MANUAL_RESEARCH = "MANUAL_RESEARCH"

# ── Statuses ────────────────────────────────────────────────────────────────
STATUS_PENDING = "PENDING"
STATUS_IN_REVIEW = "IN_REVIEW"
STATUS_COMPLETED = "COMPLETED"
STATUS_EXPIRED = "EXPIRED"
STATUS_CANCELLED = "CANCELLED"

# ── Timing ──────────────────────────────────────────────────────────────────
_CASE_TTL_SEC = 3600          # 1h expiry
_COOLDOWN_SEC = 300           # 5 min cooldown per (symbol, direction)
_MAX_ACTIVE_CASES = 50
_SCORE_CHANGE_THRESHOLD = 10  # points


class CandidateReviewCase:
    def __init__(
        self,
        case_id: str,
        symbol: str,
        direction: str,
        trigger: str,
        window: str,
        candidate_snapshot: dict[str, Any],
    ) -> None:
        self.case_id = case_id
        self.symbol = symbol
        self.direction = direction
        self.trigger = trigger
        self.window = window
        self.candidate_snapshot = candidate_snapshot
        self.status = STATUS_PENDING
        self.created_at = int(time.time() * 1000)
        self.updated_at = self.created_at
        self.completed_at: int | None = None
        self.decision: dict[str, Any] | None = None
        self.notes: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "caseId": self.case_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "trigger": self.trigger,
            "window": self.window,
            "status": self.status,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "completedAt": self.completed_at,
            "decision": self.decision,
            "notes": self.notes,
            "candidateScore": self.candidate_snapshot.get("score"),
            "candidateStage": self.candidate_snapshot.get("stage"),
            "researchOnly": True,
        }


class ReviewCaseManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cases: dict[str, CandidateReviewCase] = {}
        self._cooldowns: dict[tuple[str, str], float] = {}  # (sym, dir) -> ts
        self._total_created = 0
        self._total_expired = 0
        self._total_closed = 0

    def _dedup_key(self, symbol: str, direction: str, trigger: str) -> str:
        return f"{symbol}:{direction}:{trigger}"

    def _has_active_case(self, symbol: str, direction: str, trigger: str) -> bool:
        key = self._dedup_key(symbol, direction, trigger)
        for c in self._cases.values():
            if (
                c.symbol == symbol
                and c.direction == direction
                and c.trigger == trigger
                and c.status in (STATUS_PENDING, STATUS_IN_REVIEW)
            ):
                return True
        return False

    def _in_cooldown(self, symbol: str, direction: str) -> bool:
        ts = self._cooldowns.get((symbol, direction), 0.0)
        return time.time() - ts < _COOLDOWN_SEC

    def create_case(
        self,
        symbol: str,
        direction: str,
        trigger: str,
        candidate_snapshot: dict[str, Any],
        window: str = "5m",
        force: bool = False,
    ) -> CandidateReviewCase | None:
        with self._lock:
            self._expire_stale()

            if not force:
                if self._has_active_case(symbol, direction, trigger):
                    return None
                if trigger != TRIGGER_MANUAL_RESEARCH and self._in_cooldown(symbol, direction):
                    return None
                if len([c for c in self._cases.values() if c.status in (STATUS_PENDING, STATUS_IN_REVIEW)]) >= _MAX_ACTIVE_CASES:
                    logger.warning("[review_cases] max active cases reached")
                    return None

            case_id = str(uuid.uuid4())
            case = CandidateReviewCase(
                case_id=case_id,
                symbol=symbol,
                direction=direction,
                trigger=trigger,
                window=window,
                candidate_snapshot=dict(candidate_snapshot),
            )
            self._cases[case_id] = case
            self._total_created += 1
            get_research_store().append("review_cases", case.to_dict())

        publish_event(
            REVIEW_CASE_CREATED,
            {"caseId": case_id, "symbol": symbol, "direction": direction, "trigger": trigger},
            idempotency_key=f"case:{self._dedup_key(symbol, direction, trigger)}:{int(time.time()//60)}",
        )
        return case

    def update_case_status(
        self,
        case_id: str,
        status: str,
        decision: dict[str, Any] | None = None,
        note: str | None = None,
    ) -> bool:
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                return False
            case.status = status
            case.updated_at = int(time.time() * 1000)
            if decision:
                case.decision = decision
            if note:
                case.notes.append(note)
            if status in (STATUS_COMPLETED, STATUS_EXPIRED, STATUS_CANCELLED):
                case.completed_at = case.updated_at
                self._cooldowns[(case.symbol, case.direction)] = time.time()
                if status == STATUS_EXPIRED:
                    self._total_expired += 1
                else:
                    self._total_closed += 1

        publish_event(REVIEW_CASE_UPDATED, {"caseId": case_id, "status": status})
        if status == STATUS_EXPIRED:
            publish_event(REVIEW_CASE_EXPIRED, {"caseId": case_id})
        elif status in (STATUS_COMPLETED, STATUS_CANCELLED):
            publish_event(REVIEW_CASE_CLOSED, {"caseId": case_id, "status": status})
        return True

    def close_by_symbol_invalidation(self, symbol: str) -> int:
        """Close all pending/in-review cases for a symbol (candidate invalidated)."""
        closed = 0
        with self._lock:
            for case in self._cases.values():
                if case.symbol == symbol and case.status in (STATUS_PENDING, STATUS_IN_REVIEW):
                    case.status = STATUS_CANCELLED
                    case.updated_at = int(time.time() * 1000)
                    case.completed_at = case.updated_at
                    case.notes.append("Closed: candidate invalidated")
                    closed += 1
        if closed:
            publish_event(REVIEW_CASE_CLOSED, {"symbol": symbol, "reason": "candidate_invalidated", "count": closed})
        return closed

    def _expire_stale(self) -> None:
        now_ms = int(time.time() * 1000)
        ttl_ms = _CASE_TTL_SEC * 1000
        for case in list(self._cases.values()):
            if case.status in (STATUS_PENDING, STATUS_IN_REVIEW):
                if now_ms - case.created_at > ttl_ms:
                    case.status = STATUS_EXPIRED
                    case.completed_at = now_ms
                    self._total_expired += 1
                    publish_event(REVIEW_CASE_EXPIRED, {"caseId": case.case_id})

    def get_case(self, case_id: str) -> CandidateReviewCase | None:
        with self._lock:
            return self._cases.get(case_id)

    def list_cases(
        self,
        status: str | None = None,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._lock:
            self._expire_stale()
            cases = list(self._cases.values())
        if status:
            cases = [c for c in cases if c.status == status]
        if symbol:
            cases = [c for c in cases if c.symbol == symbol]
        cases.sort(key=lambda c: c.created_at, reverse=True)
        return [c.to_dict() for c in cases[:limit]]

    def status_summary(self) -> dict[str, Any]:
        with self._lock:
            self._expire_stale()
            pending = sum(1 for c in self._cases.values() if c.status == STATUS_PENDING)
            in_review = sum(1 for c in self._cases.values() if c.status == STATUS_IN_REVIEW)
            completed = sum(1 for c in self._cases.values() if c.status == STATUS_COMPLETED)
            expired = sum(1 for c in self._cases.values() if c.status == STATUS_EXPIRED)
            cancelled = sum(1 for c in self._cases.values() if c.status == STATUS_CANCELLED)
        return {
            "ok": True,
            "researchOnly": True,
            "totalCreated": self._total_created,
            "totalExpired": self._total_expired,
            "totalClosed": self._total_closed,
            "active": pending + in_review,
            "byStatus": {
                "PENDING": pending,
                "IN_REVIEW": in_review,
                "COMPLETED": completed,
                "EXPIRED": expired,
                "CANCELLED": cancelled,
            },
            "generatedAt": int(time.time() * 1000),
        }

    def ingest_scanner_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Create review cases from scanner long/short top lists.

        Hook from scanner_service; never modifies candidate scores.
        """
        created = 0
        skipped = 0

        def _process_list(candidates: list[dict[str, Any]], direction: str) -> None:
            nonlocal created, skipped
            for rank, c in enumerate(candidates[:5]):  # top 5
                sym = str(c.get("symbol") or "")
                if not sym:
                    continue
                stage = str(c.get("stage") or "")
                score = c.get("score") or c.get("totalScore") or 0

                # Determine trigger
                if rank < 5:
                    trigger = TRIGGER_TOP5_ENTRY
                elif stage == "CONFIRMED":
                    trigger = TRIGGER_CONFIRMED
                else:
                    continue

                case = self.create_case(
                    symbol=sym,
                    direction=direction,
                    trigger=trigger,
                    candidate_snapshot=c,
                )
                if case:
                    created += 1
                else:
                    skipped += 1

            # Also check CONFIRMED regardless of rank
            for c in candidates:
                if str(c.get("stage") or "") == "CONFIRMED":
                    sym = str(c.get("symbol") or "")
                    if not sym:
                        continue
                    case = self.create_case(
                        symbol=sym,
                        direction=direction,
                        trigger=TRIGGER_CONFIRMED,
                        candidate_snapshot=c,
                    )
                    if case:
                        created += 1
                    else:
                        skipped += 1

        longs = snapshot.get("longs") or snapshot.get("longCandidates") or []
        shorts = snapshot.get("shorts") or snapshot.get("shortCandidates") or []

        _process_list(longs, "LONG")
        _process_list(shorts, "SHORT")

        publish_event(
            SCANNER_SNAPSHOT_INGESTED,
            {"casesCreated": created, "casesSkipped": skipped},
        )
        return {"casesCreated": created, "casesSkipped": skipped}


_MANAGER: ReviewCaseManager | None = None
_MANAGER_LOCK = threading.Lock()


def get_review_case_manager() -> ReviewCaseManager:
    global _MANAGER
    with _MANAGER_LOCK:
        if _MANAGER is None:
            _MANAGER = ReviewCaseManager()
        return _MANAGER


def ingest_scanner_snapshot(snapshot: dict[str, Any]) -> None:
    """Best-effort hook callable from scanner_service. Never raises."""
    try:
        get_review_case_manager().ingest_scanner_snapshot(snapshot)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[review_cases] ingest_scanner_snapshot error (non-fatal): %s", exc)
