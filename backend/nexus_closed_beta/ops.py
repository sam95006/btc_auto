"""Lightweight product reliability counters — existing logging style, no vendor."""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

OPS_CHANNELS = (
    "auth_errors",
    "radar_api_failures",
    "watchlist_persistence_failures",
    "notification_failures",
    "market_series_failures",
)


class ProductOpsVisibility:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counts: dict[str, int] = {k: 0 for k in OPS_CHANNELS}
        self._last: dict[str, dict[str, Any]] = {}

    def record(self, channel: str, *, detail: Optional[str] = None) -> None:
        if channel not in OPS_CHANNELS:
            return
        with self._lock:
            self._counts[channel] = int(self._counts.get(channel, 0)) + 1
            self._last[channel] = {
                "ts": int(time.time() * 1000),
                "detail": (detail or "")[:200],
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "channels": dict(self._counts),
                "last": dict(self._last),
                "vendor": None,
                "external_monitoring": False,
            }


_OPS: Optional[ProductOpsVisibility] = None
_LOCK = threading.Lock()


def get_product_ops() -> ProductOpsVisibility:
    global _OPS
    with _LOCK:
        if _OPS is None:
            _OPS = ProductOpsVisibility()
        return _OPS


def record_ops(channel: str, *, detail: Optional[str] = None) -> None:
    get_product_ops().record(channel, detail=detail)
