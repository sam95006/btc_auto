"""Server-backed notification center (in-app first)."""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

from backend.nexus_paid_beta_retention.constants import NOTIFICATION_RETENTION


def _utcnow_ms() -> int:
    return int(time.time() * 1000)


class NotificationCenter:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_account: dict[str, list[dict[str, Any]]] = {}

    def list_for(self, account_id: str, *, limit: int = 50) -> dict[str, Any]:
        with self._lock:
            items = list(self._by_account.get(account_id) or [])
            items.sort(key=lambda x: int(x.get("ts") or 0), reverse=True)
            clipped = items[: max(1, min(limit, NOTIFICATION_RETENTION))]
            unread = sum(1 for i in clipped if not i.get("read"))
            return {
                "authority": "SERVER",
                "items": clipped,
                "unread": unread,
                "count": len(clipped),
                "delivery": "in_app",
                "web_push": False,
                "email": False,
            }

    def push(self, account_id: str, event: dict[str, Any]) -> dict[str, Any]:
        note = {
            "id": str(event.get("id") or f"n_{_utcnow_ms()}"),
            "ts": int(event.get("ts") or _utcnow_ms()),
            "symbol": str(event.get("symbol") or ""),
            "type": str(event.get("type") or "WATCHLIST_EVENT"),
            "severity": str(event.get("severity") or "INFO"),
            "headline": str(event.get("headline") or ""),
            "metric": event.get("metric") or {},
            "source": str(event.get("source") or "retention"),
            "read": False,
            "link": str(event.get("link") or "/alerts"),
        }
        with self._lock:
            bucket = self._by_account.setdefault(account_id, [])
            bucket.insert(0, note)
            self._by_account[account_id] = bucket[:NOTIFICATION_RETENTION]
            return note

    def mark_read(self, account_id: str, note_id: str) -> dict[str, Any]:
        with self._lock:
            for item in self._by_account.get(account_id) or []:
                if item.get("id") == note_id:
                    item["read"] = True
                    return {"ok": True, "id": note_id, "read": True}
            return {"ok": False, "id": note_id, "error": "not_found"}


_CENTER: Optional[NotificationCenter] = None
_LOCK = threading.Lock()


def get_notification_center() -> NotificationCenter:
    global _CENTER
    with _LOCK:
        if _CENTER is None:
            _CENTER = NotificationCenter()
        return _CENTER
