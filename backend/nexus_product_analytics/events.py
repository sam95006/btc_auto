"""Server-side product analytics event contract — no PII dumps, no external SaaS."""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

# Core 7-event contract preserved; V18.2.22 adds session/watchlist/notification lifecycle.
PRODUCT_EVENT_NAMES = frozenset(
    {
        "signup_completed",
        "login_completed",
        "radar_opened",
        "symbol_opened",
        "watchlist_added",
        "alert_opened",
        "returned_from_alert",
        # V18.2.22 closed-beta readiness additions (minimal PII)
        "session_started",
        "session_returned",
        "watchlist_removed",
        "notification_read",
    }
)

_MAX_EVENTS = 5000


class ProductAnalyticsStore:
    def __init__(self, *, max_events: int = _MAX_EVENTS) -> None:
        self._lock = threading.RLock()
        self._events: list[dict[str, Any]] = []
        self._max = max_events

    def record(
        self,
        name: str,
        *,
        account_id: Optional[str] = None,
        props: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if name not in PRODUCT_EVENT_NAMES:
            raise ValueError(f"unknown_product_event:{name}")
        # Never accept password / token / secret props.
        safe_props: dict[str, Any] = {}
        for k, v in (props or {}).items():
            key = str(k).lower()
            if any(x in key for x in ("password", "token", "secret", "hash", "authorization")):
                continue
            if isinstance(v, (str, int, float, bool)) or v is None:
                safe_props[str(k)] = v
        row = {
            "name": name,
            "ts": int(time.time() * 1000),
            "account_id": account_id,
            "props": safe_props,
        }
        with self._lock:
            self._events.append(row)
            if len(self._events) > self._max:
                self._events = self._events[-self._max :]
        return {"ok": True, "event": row}

    def list_events(
        self,
        *,
        account_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._events)
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        return rows[-max(1, min(200, limit)) :]

    def counts(self) -> dict[str, int]:
        with self._lock:
            out: dict[str, int] = {n: 0 for n in sorted(PRODUCT_EVENT_NAMES)}
            for e in self._events:
                n = str(e.get("name") or "")
                if n in out:
                    out[n] += 1
            return out


_STORE: Optional[ProductAnalyticsStore] = None
_LOCK = threading.Lock()


def get_analytics_store() -> ProductAnalyticsStore:
    global _STORE
    with _LOCK:
        if _STORE is None:
            _STORE = ProductAnalyticsStore()
        return _STORE


def record_event(
    name: str,
    *,
    account_id: Optional[str] = None,
    props: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return get_analytics_store().record(name, account_id=account_id, props=props)
