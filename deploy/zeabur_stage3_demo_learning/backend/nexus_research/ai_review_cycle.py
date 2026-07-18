"""6-hour AI Review Cycle scheduler (Asia/Taipei: 00:00, 06:00, 12:00, 18:00).

Session states: PENDING → RUNNING → COMPLETED | SKIPPED | FAILED.
Blocks duplicate sessions for same slot.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any

from backend.nexus_research.domain_events import (
    REVIEW_CYCLE_COMPLETED,
    REVIEW_CYCLE_SKIPPED,
    REVIEW_CYCLE_STARTED,
    publish_event,
)
from backend.nexus_research.storage import get_research_store

logger = logging.getLogger(__name__)

# ── Session state constants ──────────────────────────────────────────────────
STATE_PENDING = "PENDING"
STATE_RUNNING = "RUNNING"
STATE_COMPLETED = "COMPLETED"
STATE_SKIPPED = "SKIPPED"
STATE_FAILED = "FAILED"

_CYCLE_HOURS = (0, 6, 12, 18)  # Asia/Taipei schedule
_SESSION_HISTORY_LIMIT = 48    # keep ~5 days
_TAIPEI_UTC_OFFSET_H = 8


def _taipei_hour_now() -> int:
    """Current hour in Asia/Taipei (UTC+8)."""
    try:
        import datetime
        utc_now = datetime.datetime.utcnow()
        taipei_now = utc_now + datetime.timedelta(hours=_TAIPEI_UTC_OFFSET_H)
        return taipei_now.hour
    except Exception:  # noqa: BLE001
        return (time.gmtime().tm_hour + _TAIPEI_UTC_OFFSET_H) % 24


def _slot_key_for_hour(hour: int) -> str:
    """Return the slot key for the nearest scheduled cycle hour."""
    # round down to last scheduled hour
    scheduled = sorted(h for h in _CYCLE_HOURS if h <= hour)
    slot_h = scheduled[-1] if scheduled else max(_CYCLE_HOURS)
    import datetime
    today = datetime.datetime.utcnow() + datetime.timedelta(hours=_TAIPEI_UTC_OFFSET_H)
    day_str = today.strftime("%Y%m%d")
    return f"{day_str}_{slot_h:02d}00"


class ReviewSession:
    def __init__(self, session_id: str, slot_key: str, trigger_hour: int) -> None:
        self.session_id = session_id
        self.slot_key = slot_key
        self.trigger_hour = trigger_hour
        self.state = STATE_PENDING
        self.started_at: int | None = None
        self.completed_at: int | None = None
        self.error: str | None = None
        self.summary: dict[str, Any] = {}
        self.created_at = int(time.time() * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "slotKey": self.slot_key,
            "triggerHour": self.trigger_hour,
            "state": self.state,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "error": self.error,
            "summary": self.summary,
            "createdAt": self.created_at,
            "researchOnly": True,
        }


class AIReviewCycleScheduler:
    """6h cycle scheduler. Registered as a supervisor job."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: list[ReviewSession] = []
        self._seen_slots: set[str] = set()
        self._current_session: ReviewSession | None = None

    def _collect_session_summary(self) -> dict[str, Any]:
        """Collect non-fabricated summary of recent state."""
        summary: dict[str, Any] = {
            "collectedAt": int(time.time() * 1000),
            "researchOnly": True,
            "privateApi": False,
        }
        try:
            from backend.nexus_research.review_cases import get_review_case_manager
            mgr = get_review_case_manager()
            status = mgr.status_summary()
            summary["reviewCases"] = {
                "active": status.get("active", 0),
                "totalCreated": status.get("totalCreated", 0),
                "byStatus": status.get("byStatus", {}),
            }
        except Exception as exc:  # noqa: BLE001
            summary["reviewCasesError"] = str(exc)

        try:
            from backend.nexus_research.domain_events import get_event_bus
            bus_status = get_event_bus().status()
            summary["eventBus"] = {
                "totalPublished": bus_status.get("totalPublished", 0),
                "recentCount": bus_status.get("recentCount", 0),
            }
        except Exception as exc:  # noqa: BLE001
            summary["eventBusError"] = str(exc)

        try:
            from backend.nexus_research.storage import storage_audit
            audit = storage_audit()
            summary["storage"] = {
                "backendType": audit.get("backendType"),
                "tableCounts": audit.get("tableCounts", {}),
            }
        except Exception as exc:  # noqa: BLE001
            summary["storageError"] = str(exc)

        return summary

    def run_cycle(self) -> None:
        """Called by supervisor on schedule or manually."""
        hour = _taipei_hour_now()
        slot_key = _slot_key_for_hour(hour)

        with self._lock:
            if slot_key in self._seen_slots:
                logger.debug("[ai_review_cycle] slot %s already done — skipping", slot_key)
                publish_event(REVIEW_CYCLE_SKIPPED, {"slotKey": slot_key, "reason": "duplicate_slot"})
                return

            session_id = str(uuid.uuid4())
            session = ReviewSession(session_id=session_id, slot_key=slot_key, trigger_hour=hour)
            self._sessions.append(session)
            if len(self._sessions) > _SESSION_HISTORY_LIMIT:
                self._sessions = self._sessions[-_SESSION_HISTORY_LIMIT:]
            self._seen_slots.add(slot_key)
            self._current_session = session

        session.state = STATE_RUNNING
        session.started_at = int(time.time() * 1000)
        publish_event(REVIEW_CYCLE_STARTED, {"sessionId": session_id, "slotKey": slot_key})
        logger.info("[ai_review_cycle] cycle session %s started (slot=%s)", session_id, slot_key)

        try:
            summary = self._collect_session_summary()
            session.summary = summary
            session.state = STATE_COMPLETED
            session.completed_at = int(time.time() * 1000)
            get_research_store().append("review_sessions", session.to_dict())
            publish_event(
                REVIEW_CYCLE_COMPLETED,
                {"sessionId": session_id, "slotKey": slot_key, "summary": summary},
            )
            logger.info("[ai_review_cycle] session %s completed", session_id)
        except Exception as exc:  # noqa: BLE001
            session.state = STATE_FAILED
            session.error = str(exc)
            session.completed_at = int(time.time() * 1000)
            logger.error("[ai_review_cycle] session %s failed: %s", session_id, exc)

    def trigger_manual(self) -> str:
        """Force a new session regardless of slot dedup."""
        hour = _taipei_hour_now()
        slot_key = f"manual_{int(time.time())}"
        with self._lock:
            session_id = str(uuid.uuid4())
            session = ReviewSession(session_id=session_id, slot_key=slot_key, trigger_hour=hour)
            self._sessions.append(session)
            self._current_session = session

        session.state = STATE_RUNNING
        session.started_at = int(time.time() * 1000)

        try:
            summary = self._collect_session_summary()
            session.summary = summary
            session.state = STATE_COMPLETED
            session.completed_at = int(time.time() * 1000)
            get_research_store().append("review_sessions", session.to_dict())
        except Exception as exc:  # noqa: BLE001
            session.state = STATE_FAILED
            session.error = str(exc)
            session.completed_at = int(time.time() * 1000)

        return session_id

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            sessions = list(self._sessions)
        sessions.sort(key=lambda s: s.created_at, reverse=True)
        return [s.to_dict() for s in sessions[:limit]]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            for s in self._sessions:
                if s.session_id == session_id:
                    return s.to_dict()
        return None

    def status(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._sessions)
            last = self._sessions[-1].to_dict() if self._sessions else None
            current = self._current_session.to_dict() if self._current_session else None
            completed = sum(1 for s in self._sessions if s.state == STATE_COMPLETED)
            failed = sum(1 for s in self._sessions if s.state == STATE_FAILED)

        taipei_hour = _taipei_hour_now()
        next_slot_h = next((h for h in sorted(_CYCLE_HOURS) if h > taipei_hour), _CYCLE_HOURS[0])
        return {
            "ok": True,
            "researchOnly": True,
            "scheduleHours": list(_CYCLE_HOURS),
            "scheduleTimezone": "Asia/Taipei",
            "currentTaipeiHour": taipei_hour,
            "nextScheduledHour": next_slot_h,
            "totalSessions": total,
            "completedSessions": completed,
            "failedSessions": failed,
            "lastSession": last,
            "currentSession": current,
            "generatedAt": int(time.time() * 1000),
        }


_SCHEDULER: AIReviewCycleScheduler | None = None
_SCHEDULER_LOCK = threading.Lock()


def get_ai_review_scheduler() -> AIReviewCycleScheduler:
    global _SCHEDULER
    with _SCHEDULER_LOCK:
        if _SCHEDULER is None:
            _SCHEDULER = AIReviewCycleScheduler()
        return _SCHEDULER


def start_ai_review_supervisor_job() -> None:
    """Register the 6h cycle as a supervisor job. Call at app startup."""
    try:
        from backend.nexus_research.runtime_supervisor import get_supervisor
        scheduler = get_ai_review_scheduler()
        supervisor = get_supervisor()
        supervisor.register_job(
            job_id="ai_review_cycle_6h",
            fn=scheduler.run_cycle,
            interval_sec=21600,  # 6 hours
            timeout_sec=300,
            max_retries=1,
            backoff_sec=30.0,
        )
        supervisor.start()
        logger.info("[ai_review_cycle] 6h cycle job registered with supervisor")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ai_review_cycle] could not register supervisor job: %s", exc)
