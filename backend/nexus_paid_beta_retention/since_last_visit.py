"""Since Last Visit — requires real identity/session only."""
from __future__ import annotations

import threading
import time
from typing import Any, Optional


def _utcnow_ms() -> int:
    return int(time.time() * 1000)


class VisitTracker:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._last: dict[str, int] = {}

    def snapshot(self, account_id: str) -> dict[str, Any]:
        now = _utcnow_ms()
        with self._lock:
            prev = self._last.get(account_id)
            self._last[account_id] = now
            return {
                "account_id": account_id,
                "previous_visit_at": prev,
                "current_visit_at": now,
                "has_previous": prev is not None,
                "authority": "SERVER",
            }


_TRACKER: Optional[VisitTracker] = None
_LOCK = threading.Lock()


def get_visit_tracker() -> VisitTracker:
    global _TRACKER
    with _LOCK:
        if _TRACKER is None:
            _TRACKER = VisitTracker()
        return _TRACKER
