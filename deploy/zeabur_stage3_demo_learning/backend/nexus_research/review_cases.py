"""CandidateReviewCase manager — Phase 6.2 lifecycle recovery.

Repository is Source of Truth. Manager is a bounded natural-active working set.

ACTIVE (capacity-counted, natural only):
  OPEN, COLLECTING, UNDER_REVIEW, READY_FOR_SIMULATION, RISK_BLOCKED, WATCH_ONLY
  + legacy PENDING / IN_REVIEW when not expired / not validation / not superseded

TERMINAL:
  COMPLETED, REJECTED, EXPIRED, CANCELLED, CLOSED, SUPERSEDED, NEEDS_REVIEW_ARCHIVED

Validation namespaces are isolated from natural capacity.
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
STATUS_OPEN = "OPEN"
STATUS_COLLECTING = "COLLECTING"
STATUS_UNDER_REVIEW = "UNDER_REVIEW"
STATUS_READY_FOR_SIMULATION = "READY_FOR_SIMULATION"
STATUS_RISK_BLOCKED = "RISK_BLOCKED"
STATUS_WATCH_ONLY = "WATCH_ONLY"
STATUS_PENDING = "PENDING"          # legacy → treated as OPEN when active
STATUS_IN_REVIEW = "IN_REVIEW"      # legacy → UNDER_REVIEW
STATUS_COMPLETED = "COMPLETED"
STATUS_REJECTED = "REJECTED"
STATUS_EXPIRED = "EXPIRED"
STATUS_CANCELLED = "CANCELLED"
STATUS_CLOSED = "CLOSED"
STATUS_SUPERSEDED = "SUPERSEDED"
STATUS_NEEDS_REVIEW_ARCHIVED = "NEEDS_REVIEW_ARCHIVED"

ACTIVE_CASE_STATUSES = {
    STATUS_OPEN,
    STATUS_COLLECTING,
    STATUS_UNDER_REVIEW,
    STATUS_READY_FOR_SIMULATION,
    STATUS_RISK_BLOCKED,
    STATUS_WATCH_ONLY,
    STATUS_PENDING,
    STATUS_IN_REVIEW,
}

TERMINAL_CASE_STATUSES = {
    STATUS_COMPLETED,
    STATUS_REJECTED,
    STATUS_EXPIRED,
    STATUS_CANCELLED,
    STATUS_CLOSED,
    STATUS_SUPERSEDED,
    STATUS_NEEDS_REVIEW_ARCHIVED,
}

VALIDATION_TYPES = {
    "PERSISTENCE_VALIDATION",
    "MANUAL_RESEARCH_VALIDATION",
    "REPLAY_VALIDATION",
}

_TRIGGER_PRIORITY = {
    TRIGGER_POSITION_RISK: 100,
    TRIGGER_MAJOR_ANOMALY: 90,
    TRIGGER_CONFIRMED: 80,
    TRIGGER_TOP5_ENTRY: 70,
    STATUS_READY_FOR_SIMULATION: 75,
    TRIGGER_SCORE_CHANGE: 40,
    TRIGGER_SCHEDULED_REVIEW: 30,
    TRIGGER_MANUAL_RESEARCH: 20,
    "WATCH_ONLY": 10,
}

# ── Timing / capacity ───────────────────────────────────────────────────────
_CASE_TTL_SEC = 3600
_STALE_EVIDENCE_SEC = 7200
_COOLDOWN_SEC = 300
_MAX_ACTIVE_CASES = 50
_HYDRATE_LIMIT = 50
_SWEEP_BATCH = 200
_SCORE_CHANGE_THRESHOLD = 10

# Log rate limit for capacity blocks
_CAPACITY_LOG_INTERVAL_SEC = 60.0


def _now_ms() -> int:
    return int(time.time() * 1000)


def _validation_type(snapshot: dict[str, Any] | None, row: dict[str, Any] | None = None) -> str:
    for src in (snapshot or {}, row or {}):
        vt = str(
            src.get("validationType")
            or src.get("validation_type")
            or src.get("quotaNamespace")
            or ""
        ).strip().upper()
        if vt in VALIDATION_TYPES:
            return vt
        label = str(src.get("validationRound") or src.get("validation_label") or "")
        if "PERSISTENCE_VALIDATION" in label or "PHASE61_RESTART_PROOF" in label:
            return "PERSISTENCE_VALIDATION"
        if src.get("excludeFromNaturalPaperPnl") or src.get("validationOnly"):
            return "PERSISTENCE_VALIDATION"
        if str(src.get("trigger") or "") == TRIGGER_MANUAL_RESEARCH and src.get("validationType"):
            return str(src.get("validationType")).upper()
    return ""


def _is_validation(snapshot: dict[str, Any] | None, row: dict[str, Any] | None = None) -> bool:
    return _validation_type(snapshot, row) in VALIDATION_TYPES


def _setup_identity(snapshot: dict[str, Any], window: str) -> str:
    return str(
        snapshot.get("setupId")
        or snapshot.get("setupIdentity")
        or snapshot.get("candidateId")
        or snapshot.get("fingerprint")
        or f"{snapshot.get('stage') or ''}:{window}:{snapshot.get('score') or ''}"
    )


def _natural_key(symbol: str, side: str, setup: str, window: str) -> str:
    return f"{symbol}|{side}|{setup}|{window}"


def _normalize_status(status: str) -> str:
    s = (status or STATUS_PENDING).upper()
    if s == STATUS_PENDING:
        return STATUS_OPEN  # mapping for new writes; hydrate may keep PENDING until sweep
    if s == STATUS_IN_REVIEW:
        return STATUS_UNDER_REVIEW
    return s


class CandidateReviewCase:
    def __init__(
        self,
        case_id: str,
        symbol: str,
        direction: str,
        trigger: str,
        window: str,
        candidate_snapshot: dict[str, Any],
        *,
        validation_type: str = "",
        expires_at: int | None = None,
    ) -> None:
        self.case_id = case_id
        self.symbol = symbol
        self.direction = direction
        self.trigger = trigger
        self.window = window
        self.candidate_snapshot = candidate_snapshot
        self.validation_type = validation_type or _validation_type(candidate_snapshot)
        self.status = STATUS_OPEN if not self.validation_type else STATUS_OPEN
        self.created_at = _now_ms()
        self.updated_at = self.created_at
        self.expires_at = expires_at or (self.created_at + _CASE_TTL_SEC * 1000)
        self.completed_at: int | None = None
        self.decision: dict[str, Any] | None = None
        self.notes: list[str] = []
        self.superseded_by: str | None = None
        self.quota_namespace = self.validation_type or "NATURAL"

    @property
    def setup_identity(self) -> str:
        return _setup_identity(self.candidate_snapshot, self.window)

    @property
    def natural_key(self) -> str:
        return _natural_key(self.symbol, self.direction, self.setup_identity, self.window)

    @property
    def is_validation(self) -> bool:
        return self.validation_type in VALIDATION_TYPES

    def is_active(self, now_ms: int | None = None) -> bool:
        now = now_ms if now_ms is not None else _now_ms()
        if self.status in TERMINAL_CASE_STATUSES:
            return False
        if self.status not in ACTIVE_CASE_STATUSES:
            return False
        if self.expires_at and now >= int(self.expires_at):
            return False
        return True

    def is_natural_active(self, now_ms: int | None = None) -> bool:
        return self.is_active(now_ms) and not self.is_validation

    def priority(self) -> int:
        return int(_TRIGGER_PRIORITY.get(self.trigger, 10))

    def to_dict(self) -> dict[str, Any]:
        return {
            "caseId": self.case_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "side": self.direction,
            "trigger": self.trigger,
            "window": self.window,
            "status": self.status,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "expiresAt": self.expires_at,
            "completedAt": self.completed_at,
            "decision": self.decision,
            "notes": self.notes,
            "candidateScore": self.candidate_snapshot.get("score"),
            "candidateStage": self.candidate_snapshot.get("stage"),
            "candidateId": self.candidate_snapshot.get("candidateId")
            or self.candidate_snapshot.get("id"),
            "setupIdentity": self.setup_identity,
            "validationType": self.validation_type or None,
            "quotaNamespace": self.quota_namespace,
            "supersededBy": self.superseded_by,
            "correlationId": self.candidate_snapshot.get("correlationId"),
            "researchOnly": True,
            "excludeFromNaturalPaperPnl": self.is_validation,
        }


class ReviewCaseManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cases: dict[str, CandidateReviewCase] = {}
        self._cooldowns: dict[tuple[str, str], float] = {}
        self._total_created = 0
        self._total_updated = 0
        self._total_expired = 0
        self._total_closed = 0
        self._total_superseded = 0
        self._total_blocked_capacity = 0
        self._total_duplicate_blocked = 0
        self._hydrated = False
        self._hydrate_stats: dict[str, Any] = {}
        self._sweep_stats: dict[str, Any] = {
            "scanned": 0,
            "expired": 0,
            "superseded": 0,
            "completed": 0,
            "skipped": 0,
            "failed": 0,
            "durationMs": 0,
            "lastSuccess": None,
        }
        self._capacity_log_ts = 0.0
        self._capacity_suppressed = 0
        self._ownership_blocked = False

    # ── Persistence helpers ─────────────────────────────────────────────────

    def _persist(self, case: CandidateReviewCase) -> None:
        try:
            get_research_store().upsert("review_cases", case.to_dict())
        except Exception as exc:  # noqa: BLE001
            logger.warning("[review_cases] persist failed case=%s: %s", case.case_id, exc)

    def _row_to_case(self, row: dict[str, Any]) -> CandidateReviewCase | None:
        cid = str(row.get("caseId") or row.get("case_id") or "")
        if not cid:
            return None
        snap = dict(row.get("candidateSnapshot") or row.get("candidate_snapshot") or {})
        # Recover snapshot fields from flat row if needed
        if not snap and row.get("candidateScore") is not None:
            snap = {
                "score": row.get("candidateScore"),
                "stage": row.get("candidateStage"),
                "symbol": row.get("symbol"),
                "candidateId": row.get("candidateId"),
            }
        vt = _validation_type(snap, row)
        case = CandidateReviewCase(
            case_id=cid,
            symbol=str(row.get("symbol") or ""),
            direction=str(row.get("direction") or row.get("side") or "LONG"),
            trigger=str(row.get("trigger") or TRIGGER_MANUAL_RESEARCH),
            window=str(row.get("window") or "5m"),
            candidate_snapshot=snap,
            validation_type=vt,
            expires_at=int(row.get("expiresAt") or row.get("expires_at") or 0) or None,
        )
        case.status = str(row.get("status") or STATUS_PENDING)
        case.created_at = int(row.get("createdAt") or row.get("created_at") or _now_ms())
        case.updated_at = int(row.get("updatedAt") or row.get("updated_at") or case.created_at)
        if not case.expires_at:
            case.expires_at = case.created_at + _CASE_TTL_SEC * 1000
        case.completed_at = row.get("completedAt") or row.get("completed_at")
        case.decision = row.get("decision")
        case.notes = list(row.get("notes") or [])
        case.superseded_by = row.get("supersededBy")
        case.quota_namespace = vt or "NATURAL"
        return case

    # ── Hydration (bounded natural active only) ─────────────────────────────

    def hydrate_from_store(self, limit: int = _HYDRATE_LIMIT) -> dict[str, Any]:
        """Load only bounded natural-active cases. Never republish CREATED events."""
        with self._lock:
            if self._hydrated:
                return dict(self._hydrate_stats)

            # Lifecycle sweep BEFORE hydrate so capacity is honest.
            sweep = self._lifecycle_sweep_unlocked(persist=True, reason="hydrate")
            loaded = 0
            skipped = 0
            try:
                rows = get_research_store().query_cases(
                    statuses=sorted(ACTIVE_CASE_STATUSES),
                    exclude_validation=True,
                    limit=max(limit * 3, 150),
                    order_desc=True,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("[review_cases] hydrate failed: %s", exc)
                self._hydrate_stats = {"ok": False, "error": str(exc), "review_cases_loaded": 0}
                return dict(self._hydrate_stats)

            now = _now_ms()
            # Prefer highest priority, then newest
            candidates: list[CandidateReviewCase] = []
            for row in rows:
                case = self._row_to_case(row)
                if case is None:
                    continue
                if not case.is_natural_active(now):
                    skipped += 1
                    continue
                candidates.append(case)

            candidates.sort(key=lambda c: (-c.priority(), -c.updated_at))
            seen_keys: set[str] = set()
            for case in candidates:
                if len(self._cases) >= limit:
                    break
                key = case.natural_key
                if key in seen_keys:
                    # Duplicate natural key → supersede older in DB, skip hydrate
                    case.status = STATUS_SUPERSEDED
                    case.completed_at = now
                    case.notes.append("Hydrate: superseded by newer natural key peer")
                    self._persist(case)
                    skipped += 1
                    continue
                seen_keys.add(key)
                self._cases[case.case_id] = case
                loaded += 1

            self._hydrated = True
            self._hydrate_stats = {
                "ok": True,
                "review_cases_loaded": loaded,
                "skipped": skipped,
                "sweep": sweep,
                "hydrate_duplicate_events": 0,
                "hydrate_duplicate_cases": 0,
                "boundedLimit": limit,
                "researchOnly": True,
            }
            logger.info(
                "[review_cases] hydrated %d natural-active (skipped=%d sweep_expired=%s)",
                loaded,
                skipped,
                sweep.get("expired"),
            )
            return dict(self._hydrate_stats)

    # ── Lifecycle sweep ─────────────────────────────────────────────────────

    def lifecycle_sweep(self, *, persist: bool = True) -> dict[str, Any]:
        with self._lock:
            return self._lifecycle_sweep_unlocked(persist=persist, reason="api")

    def _lifecycle_sweep_unlocked(self, *, persist: bool, reason: str) -> dict[str, Any]:
        t0 = time.time()
        metrics = {
            "scanned": 0,
            "expired": 0,
            "superseded": 0,
            "completed": 0,
            "skipped": 0,
            "failed": 0,
            "reason": reason,
        }
        now = _now_ms()
        store = get_research_store()

        # 1) Sweep in-memory working set
        for case in list(self._cases.values()):
            metrics["scanned"] += 1
            try:
                if case.status in TERMINAL_CASE_STATUSES:
                    metrics["skipped"] += 1
                    continue
                if now >= int(case.expires_at or 0):
                    self._transition_terminal(case, STATUS_EXPIRED, "expiresAt reached", persist=persist)
                    metrics["expired"] += 1
                    continue
                stage = str(case.candidate_snapshot.get("stage") or "")
                if stage.upper() in ("INVALID", "DEAD", "REMOVED"):
                    self._transition_terminal(case, STATUS_EXPIRED, "candidate stage invalid", persist=persist)
                    metrics["expired"] += 1
                    continue
                if now - case.updated_at > _STALE_EVIDENCE_SEC * 1000 and case.status in (
                    STATUS_PENDING, STATUS_OPEN, STATUS_WATCH_ONLY
                ):
                    self._transition_terminal(
                        case, STATUS_EXPIRED, "stale evidence / no updates", persist=persist
                    )
                    metrics["expired"] += 1
            except Exception:  # noqa: BLE001
                metrics["failed"] += 1

        # 2) Bounded repository sweep for legacy PENDING / active statuses
        try:
            rows = store.query_cases(
                statuses=sorted(ACTIVE_CASE_STATUSES),
                limit=_SWEEP_BATCH,
                order_desc=False,  # oldest first
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[review_cases] repo sweep query failed: %s", exc)
            rows = []

        # Natural-key newest wins
        newest_by_key: dict[str, tuple[int, str]] = {}
        parsed: list[CandidateReviewCase] = []
        for row in rows:
            case = self._row_to_case(row)
            if case is None:
                continue
            parsed.append(case)
            metrics["scanned"] += 1
            key = case.natural_key
            prev = newest_by_key.get(key)
            if prev is None or case.updated_at >= prev[0]:
                newest_by_key[key] = (case.updated_at, case.case_id)

        for case in parsed:
            try:
                if case.status in TERMINAL_CASE_STATUSES:
                    metrics["skipped"] += 1
                    continue
                # Historical PENDING with no reliable activity → archive/expire
                if case.status == STATUS_PENDING and now >= int(case.expires_at or 0):
                    case.status = STATUS_EXPIRED
                    case.completed_at = now
                    case.updated_at = now
                    case.notes.append("Sweep: legacy PENDING expired")
                    if persist:
                        self._persist(case)
                    if case.case_id in self._cases:
                        self._cases[case.case_id] = case
                    metrics["expired"] += 1
                    self._total_expired += 1
                    publish_event(REVIEW_CASE_EXPIRED, {"caseId": case.case_id, "reason": "sweep_ttl"})
                    continue

                newest = newest_by_key.get(case.natural_key)
                if newest and newest[1] != case.case_id and case.is_active(now):
                    case.status = STATUS_SUPERSEDED
                    case.superseded_by = newest[1]
                    case.completed_at = now
                    case.updated_at = now
                    case.notes.append(f"Sweep: superseded by {newest[1]}")
                    if persist:
                        self._persist(case)
                    self._cases.pop(case.case_id, None)
                    metrics["superseded"] += 1
                    self._total_superseded += 1
                    publish_event(
                        REVIEW_CASE_CLOSED,
                        {"caseId": case.case_id, "status": STATUS_SUPERSEDED, "supersededBy": newest[1]},
                    )
                    continue

                if case.is_validation and case.status == STATUS_COMPLETED:
                    metrics["completed"] += 1
                    continue

                if not case.is_active(now) and case.status in ACTIVE_CASE_STATUSES:
                    case.status = STATUS_EXPIRED
                    case.completed_at = now
                    case.updated_at = now
                    if persist:
                        self._persist(case)
                    self._cases.pop(case.case_id, None)
                    metrics["expired"] += 1
                    self._total_expired += 1
            except Exception:  # noqa: BLE001
                metrics["failed"] += 1

        # 3) Cap natural active in manager via explicit supersede of lowest priority
        natural = [c for c in self._cases.values() if c.is_natural_active(now)]
        if len(natural) > _MAX_ACTIVE_CASES:
            natural.sort(key=lambda c: (c.priority(), c.updated_at))  # lowest first
            overflow = natural[: max(0, len(natural) - _MAX_ACTIVE_CASES)]
            for case in overflow:
                self._transition_terminal(
                    case,
                    STATUS_SUPERSEDED,
                    "capacity recovery: lowest priority released",
                    persist=persist,
                )
                metrics["superseded"] += 1

        duration_ms = int((time.time() - t0) * 1000)
        metrics["durationMs"] = duration_ms
        metrics["lastSuccess"] = _now_ms()
        self._sweep_stats = dict(metrics)
        return metrics

    def _transition_terminal(
        self,
        case: CandidateReviewCase,
        status: str,
        note: str,
        *,
        persist: bool,
    ) -> None:
        case.status = status
        case.updated_at = _now_ms()
        case.completed_at = case.updated_at
        case.notes.append(note)
        self._cooldowns[(case.symbol, case.direction)] = time.time()
        if status == STATUS_EXPIRED:
            self._total_expired += 1
            publish_event(REVIEW_CASE_EXPIRED, {"caseId": case.case_id, "reason": note})
        elif status == STATUS_SUPERSEDED:
            self._total_superseded += 1
            publish_event(REVIEW_CASE_CLOSED, {"caseId": case.case_id, "status": status})
        else:
            self._total_closed += 1
            publish_event(REVIEW_CASE_CLOSED, {"caseId": case.case_id, "status": status})
        if persist:
            self._persist(case)
        # Drop from working set when terminal
        self._cases.pop(case.case_id, None)

    # ── Admission ───────────────────────────────────────────────────────────

    def _natural_active_cases(self) -> list[CandidateReviewCase]:
        now = _now_ms()
        return [c for c in self._cases.values() if c.is_natural_active(now)]

    def _find_active_by_natural_key(self, key: str) -> CandidateReviewCase | None:
        now = _now_ms()
        for c in self._cases.values():
            if c.natural_key == key and c.is_active(now):
                return c
        return None

    def _log_capacity_block(self) -> None:
        self._total_blocked_capacity += 1
        now = time.time()
        if now - self._capacity_log_ts >= _CAPACITY_LOG_INTERVAL_SEC:
            suppressed = self._capacity_suppressed
            self._capacity_suppressed = 0
            self._capacity_log_ts = now
            logger.warning(
                "[review_cases] max active cases reached (suppressed=%d blocked_total=%d)",
                suppressed,
                self._total_blocked_capacity,
            )
        else:
            self._capacity_suppressed += 1

    def set_ownership_blocked(self, blocked: bool) -> None:
        self._ownership_blocked = bool(blocked)

    def create_case(
        self,
        symbol: str,
        direction: str,
        trigger: str,
        candidate_snapshot: dict[str, Any],
        window: str = "5m",
        force: bool = False,
        *,
        validation_type: str = "",
    ) -> CandidateReviewCase | None:
        with self._lock:
            self._lifecycle_sweep_unlocked(persist=True, reason="admission")

            if self._ownership_blocked and not force:
                logger.warning("[review_cases] ownership degraded — refusing new cases")
                return None

            vt = validation_type or _validation_type(candidate_snapshot)
            is_validation = vt in VALIDATION_TYPES
            setup = _setup_identity(candidate_snapshot, window)
            key = _natural_key(symbol, direction, setup, window)

            # Duplicate natural active → update existing (no new case)
            existing = self._find_active_by_natural_key(key)
            if existing and not force:
                existing.candidate_snapshot = dict(candidate_snapshot)
                existing.updated_at = _now_ms()
                existing.expires_at = existing.updated_at + _CASE_TTL_SEC * 1000
                if existing.trigger != trigger and _TRIGGER_PRIORITY.get(trigger, 0) > existing.priority():
                    existing.trigger = trigger
                existing.notes.append(f"Updated snapshot ({trigger})")
                self._total_updated += 1
                self._total_duplicate_blocked += 1
                self._persist(existing)
                publish_event(
                    REVIEW_CASE_UPDATED,
                    {"caseId": existing.case_id, "status": existing.status, "reason": "duplicate_snapshot"},
                )
                return existing

            if not force and not is_validation:
                if trigger != TRIGGER_MANUAL_RESEARCH and self._in_cooldown(symbol, direction):
                    return None
                natural_count = len(self._natural_active_cases())
                if natural_count >= _MAX_ACTIVE_CASES:
                    # Higher-priority triggers may displace lower-priority actives
                    # (never silent-delete; explicit SUPERSEDED transition).
                    new_pri = int(_TRIGGER_PRIORITY.get(trigger, 0))
                    if new_pri >= 70:
                        victims = sorted(
                            self._natural_active_cases(),
                            key=lambda c: (c.priority(), c.updated_at),
                        )
                        displaced = False
                        now_ms = _now_ms()
                        for v in victims:
                            stale_peer = (
                                v.priority() == new_pri
                                and (now_ms - v.updated_at) > 600_000
                            )
                            if v.priority() < new_pri or stale_peer:
                                self._transition_terminal(
                                    v,
                                    STATUS_SUPERSEDED,
                                    f"displaced by higher/equal-stale trigger {trigger}",
                                    persist=True,
                                )
                                displaced = True
                                break
                        if not displaced:
                            self._log_capacity_block()
                            return None
                    else:
                        self._log_capacity_block()
                        return None

            case_id = str(uuid.uuid4())
            case = CandidateReviewCase(
                case_id=case_id,
                symbol=symbol,
                direction=direction,
                trigger=trigger,
                window=window,
                candidate_snapshot=dict(candidate_snapshot),
                validation_type=vt,
            )
            if trigger == TRIGGER_MAJOR_ANOMALY:
                case.status = STATUS_OPEN
            elif trigger in (TRIGGER_TOP5_ENTRY, TRIGGER_CONFIRMED):
                case.status = STATUS_OPEN
            else:
                case.status = STATUS_WATCH_ONLY if trigger == TRIGGER_SCORE_CHANGE else STATUS_OPEN

            self._cases[case_id] = case
            self._total_created += 1
            self._persist(case)

        publish_event(
            REVIEW_CASE_CREATED,
            {
                "caseId": case_id,
                "symbol": symbol,
                "direction": direction,
                "trigger": trigger,
                "validationType": vt or None,
            },
            idempotency_key=f"case:{key}:{int(time.time() // 60)}",
        )
        if not is_validation:
            try:
                self.run_instant_role_review(case_id)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[review_cases] instant role review deferred: %s", exc)
        return self._cases.get(case_id) or case

    def _in_cooldown(self, symbol: str, direction: str) -> bool:
        ts = self._cooldowns.get((symbol, direction), 0.0)
        return time.time() - ts < _COOLDOWN_SEC

    def run_instant_role_review(self, case_id: str) -> dict[str, Any] | None:
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                return None
            if case.decision:
                return case.decision
            if case.is_validation:
                return None
            snapshot = dict(case.candidate_snapshot)
            symbol = case.symbol
            direction = case.direction
            active = len(self._natural_active_cases())

        self.update_case_status(case_id, STATUS_UNDER_REVIEW)
        from backend.nexus_research.roles import DecisionOrchestrator

        cand = dict(snapshot)
        cand.setdefault("symbol", symbol)
        cand.setdefault("side", direction)
        decision = DecisionOrchestrator().run(
            case_id,
            cand,
            {"activeCases": active, "triggerType": "INSTANT_CASE"},
        )
        self.update_case_status(case_id, STATUS_COMPLETED, decision=decision)
        return decision

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
                # Try repository for terminal updates
                row = get_research_store().get_by_pk("review_cases", case_id)
                if not row:
                    return False
                case = self._row_to_case(row)
                if case is None:
                    return False
                self._cases[case_id] = case

            case.status = status
            case.updated_at = _now_ms()
            if decision:
                case.decision = decision
            if note:
                case.notes.append(note)
            if status in TERMINAL_CASE_STATUSES:
                case.completed_at = case.updated_at
                self._cooldowns[(case.symbol, case.direction)] = time.time()
                if status == STATUS_EXPIRED:
                    self._total_expired += 1
                elif status == STATUS_SUPERSEDED:
                    self._total_superseded += 1
                else:
                    self._total_closed += 1
                self._persist(case)
                self._cases.pop(case_id, None)
            else:
                self._persist(case)

        publish_event(REVIEW_CASE_UPDATED, {"caseId": case_id, "status": status})
        if status == STATUS_EXPIRED:
            publish_event(REVIEW_CASE_EXPIRED, {"caseId": case_id})
        elif status in (STATUS_COMPLETED, STATUS_CANCELLED, STATUS_CLOSED, STATUS_SUPERSEDED, STATUS_REJECTED):
            publish_event(REVIEW_CASE_CLOSED, {"caseId": case_id, "status": status})
        return True

    def close_by_symbol_invalidation(self, symbol: str) -> int:
        closed = 0
        with self._lock:
            for case in list(self._cases.values()):
                if case.symbol == symbol and case.is_active():
                    self._transition_terminal(
                        case, STATUS_CANCELLED, "Closed: candidate invalidated", persist=True
                    )
                    closed += 1
        if closed:
            publish_event(
                REVIEW_CASE_CLOSED,
                {"symbol": symbol, "reason": "candidate_invalidated", "count": closed},
            )
        return closed

    def get_case(self, case_id: str) -> CandidateReviewCase | None:
        with self._lock:
            hit = self._cases.get(case_id)
            if hit:
                return hit
        row = get_research_store().get_by_pk("review_cases", case_id)
        if row:
            return self._row_to_case(row)
        return None

    def list_cases(
        self,
        status: str | None = None,
        symbol: str | None = None,
        limit: int = 50,
        *,
        view: str | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List cases. view ∈ active|historical|validation|replay|terminal|None."""
        with self._lock:
            self._lifecycle_sweep_unlocked(persist=True, reason="list")

        view_l = (view or "").lower()
        store = get_research_store()

        if view_l == "active":
            with self._lock:
                cases = [c for c in self._cases.values() if c.is_natural_active()]
            if status:
                cases = [c for c in cases if c.status == status]
            if symbol:
                cases = [c for c in cases if c.symbol == symbol]
            cases.sort(key=lambda c: c.updated_at, reverse=True)
            return [c.to_dict() for c in cases[offset : offset + limit]]

        if view_l == "validation":
            rows = store.query_cases(
                validation_types=sorted(VALIDATION_TYPES),
                symbol=symbol,
                limit=limit,
                offset=offset,
            )
            if status:
                rows = [r for r in rows if str(r.get("status")) == status]
            for r in rows:
                r.setdefault("researchOnly", True)
                r["_source"] = "repository"
            return rows[:limit]

        if view_l == "replay":
            rows = store.query_cases(
                validation_types=["REPLAY_VALIDATION"],
                symbol=symbol,
                limit=limit,
                offset=offset,
            )
            for r in rows:
                r.setdefault("researchOnly", True)
            return rows[:limit]

        if view_l in ("historical", "terminal"):
            rows = store.query_cases(
                statuses=sorted(TERMINAL_CASE_STATUSES),
                symbol=symbol,
                limit=limit,
                offset=offset,
            )
            if status:
                rows = [r for r in rows if str(r.get("status")) == status]
            for r in rows:
                r.setdefault("researchOnly", True)
                r["_source"] = "repository"
            return rows[:limit]

        # Default: manager working set + bounded repo fill
        with self._lock:
            cases = list(self._cases.values())
        if status:
            cases = [c for c in cases if c.status == status]
        if symbol:
            cases = [c for c in cases if c.symbol == symbol]
        cases.sort(key=lambda c: c.created_at, reverse=True)
        result = [c.to_dict() for c in cases[offset : offset + limit]]

        if len(result) < limit:
            try:
                rows = store.query_cases(
                    statuses=[status] if status else None,
                    symbol=symbol,
                    limit=limit,
                    offset=offset,
                )
                seen = {r.get("caseId") for r in result}
                for row in rows:
                    cid = str(row.get("caseId") or row.get("case_id") or "")
                    if not cid or cid in seen:
                        continue
                    row = {**row, "caseId": cid, "researchOnly": True, "_source": "repository"}
                    result.append(row)
                    seen.add(cid)
                    if len(result) >= limit:
                        break
            except Exception as exc:  # noqa: BLE001
                logger.debug("[review_cases] repository list fallback failed: %s", exc)
        return result[:limit]

    def status_summary(self) -> dict[str, Any]:
        with self._lock:
            self._lifecycle_sweep_unlocked(persist=True, reason="status")
            now = _now_ms()
            natural_active = [c for c in self._cases.values() if c.is_natural_active(now)]
            validation_active = [
                c for c in self._cases.values() if c.is_validation and c.is_active(now)
            ]
            by_status: dict[str, int] = {}
            for c in self._cases.values():
                by_status[c.status] = by_status.get(c.status, 0) + 1

        try:
            repo_total = get_research_store().count("review_cases")
            repo_terminal = get_research_store().count_cases(
                statuses=sorted(TERMINAL_CASE_STATUSES)
            )
        except Exception:  # noqa: BLE001
            repo_total = 0
            repo_terminal = 0

        return {
            "ok": True,
            "researchOnly": True,
            "totalCreated": self._total_created,
            "totalUpdated": self._total_updated,
            "totalExpired": self._total_expired,
            "totalClosed": self._total_closed,
            "totalSuperseded": self._total_superseded,
            "active": len(natural_active),
            "naturalActive": len(natural_active),
            "validationActiveExcluded": len(validation_active),
            "configuredNaturalCapacity": _MAX_ACTIVE_CASES,
            "capacityAvailable": max(0, _MAX_ACTIVE_CASES - len(natural_active)),
            "capacityBlockedTotal": self._total_blocked_capacity,
            "capacityLogSuppressed": self._capacity_suppressed,
            "duplicateBlocked": self._total_duplicate_blocked,
            "repositoryTotal": repo_total,
            "repositoryTerminalApprox": repo_terminal,
            "ownershipBlocked": self._ownership_blocked,
            "byStatus": {
                "PENDING": by_status.get(STATUS_PENDING, 0),
                "OPEN": by_status.get(STATUS_OPEN, 0),
                "UNDER_REVIEW": by_status.get(STATUS_UNDER_REVIEW, 0) + by_status.get(STATUS_IN_REVIEW, 0),
                "IN_REVIEW": by_status.get(STATUS_IN_REVIEW, 0),
                "COMPLETED": by_status.get(STATUS_COMPLETED, 0),
                "EXPIRED": by_status.get(STATUS_EXPIRED, 0),
                "CANCELLED": by_status.get(STATUS_CANCELLED, 0),
                "SUPERSEDED": by_status.get(STATUS_SUPERSEDED, 0),
                **{k: v for k, v in by_status.items() if k not in {
                    STATUS_PENDING, STATUS_OPEN, STATUS_UNDER_REVIEW, STATUS_IN_REVIEW,
                    STATUS_COMPLETED, STATUS_EXPIRED, STATUS_CANCELLED, STATUS_SUPERSEDED,
                }},
            },
            "sweep": dict(self._sweep_stats),
            "hydrate": dict(self._hydrate_stats),
            "generatedAt": _now_ms(),
        }

    def ingest_scanner_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Create/update review cases from scanner top lists. Never modifies scores."""
        created = 0
        updated = 0
        skipped = 0
        superseded_out_of_top = 0

        keep_keys: set[str] = set()

        def _process_list(candidates: list[dict[str, Any]], direction: str) -> None:
            nonlocal created, updated, skipped
            for rank, c in enumerate(candidates[:5]):
                sym = str(c.get("symbol") or "")
                if not sym:
                    continue
                setup = _setup_identity(c, "5m")
                keep_keys.add(_natural_key(sym, direction, setup, "5m"))
                # Also keep symbol+side loosely for top-5 membership
                keep_keys.add(f"{sym}|{direction}|*")
                before = self._find_active_by_natural_key(_natural_key(sym, direction, setup, "5m"))
                case = self.create_case(
                    symbol=sym,
                    direction=direction,
                    trigger=TRIGGER_TOP5_ENTRY,
                    candidate_snapshot=c,
                )
                if case is None:
                    skipped += 1
                elif before is not None and before.case_id == case.case_id:
                    updated += 1
                elif case.notes and "Updated snapshot" in (case.notes[-1] or ""):
                    updated += 1
                else:
                    created += 1

            for c in candidates:
                if str(c.get("stage") or "") != "CONFIRMED":
                    continue
                sym = str(c.get("symbol") or "")
                if not sym:
                    continue
                setup = _setup_identity(c, "5m")
                keep_keys.add(_natural_key(sym, direction, setup, "5m"))
                keep_keys.add(f"{sym}|{direction}|*")
                case = self.create_case(
                    symbol=sym,
                    direction=direction,
                    trigger=TRIGGER_CONFIRMED,
                    candidate_snapshot=c,
                )
                if case is None:
                    skipped += 1
                elif case.notes and "Updated snapshot" in (case.notes[-1] or ""):
                    updated += 1
                else:
                    created += 1

        longs = snapshot.get("longs") or snapshot.get("longCandidates") or []
        shorts = snapshot.get("shorts") or snapshot.get("shortCandidates") or []
        _process_list(longs, "LONG")
        _process_list(shorts, "SHORT")

        # Release capacity: supersede natural actives no longer in current top/confirmed set
        with self._lock:
            now = _now_ms()
            for case in list(self._cases.values()):
                if not case.is_natural_active(now):
                    continue
                if case.trigger in (
                    TRIGGER_POSITION_RISK,
                    TRIGGER_MAJOR_ANOMALY,
                    TRIGGER_CONFIRMED,
                    TRIGGER_SCHEDULED_REVIEW,
                ):
                    continue
                loose = f"{case.symbol}|{case.direction}|*"
                if case.natural_key in keep_keys or loose in keep_keys:
                    continue
                if case.trigger in (TRIGGER_TOP5_ENTRY, TRIGGER_SCORE_CHANGE):
                    self._transition_terminal(
                        case,
                        STATUS_SUPERSEDED,
                        "no longer in scanner top5",
                        persist=True,
                    )
                    superseded_out_of_top += 1

        publish_event(
            SCANNER_SNAPSHOT_INGESTED,
            {
                "casesCreated": created,
                "casesUpdated": updated,
                "casesSkipped": skipped,
                "casesSupersededOutOfTop": superseded_out_of_top,
            },
        )
        return {
            "casesCreated": created,
            "casesUpdated": updated,
            "casesSkipped": skipped,
            "casesSupersededOutOfTop": superseded_out_of_top,
        }


_MANAGER: ReviewCaseManager | None = None
_MANAGER_LOCK = threading.Lock()


def get_review_case_manager() -> ReviewCaseManager:
    global _MANAGER
    with _MANAGER_LOCK:
        if _MANAGER is None:
            _MANAGER = ReviewCaseManager()
            try:
                _MANAGER.hydrate_from_store()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[review_cases] startup hydrate deferred: %s", exc)
        return _MANAGER


def reset_review_case_manager_for_tests() -> None:
    global _MANAGER
    with _MANAGER_LOCK:
        _MANAGER = None


def ingest_scanner_snapshot(snapshot: dict[str, Any]) -> None:
    try:
        get_review_case_manager().ingest_scanner_snapshot(snapshot)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[review_cases] ingest_scanner_snapshot error (non-fatal): %s", exc)
