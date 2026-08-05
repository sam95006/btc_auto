"""Staleness classification for public realtime streams."""
from __future__ import annotations

import time
from typing import Any

from backend.nexus_public_realtime_transport.constants import (
    HEARTBEAT_INTERVAL_SECONDS,
    STALE_AFTER_SECONDS,
)


def classify_staleness(
    *,
    last_event_ts_ms: int | None,
    now_ms: int | None = None,
    stale_after_seconds: float = STALE_AFTER_SECONDS,
    heartbeat_interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS,
) -> dict[str, Any]:
    now = int(time.time() * 1000) if now_ms is None else int(now_ms)
    if last_event_ts_ms is None or last_event_ts_ms <= 0:
        return {
            "band": "unavailable",
            "age_seconds": None,
            "stale": True,
            "needs_reconnect": True,
            "heartbeat_interval_seconds": heartbeat_interval_seconds,
            "stale_after_seconds": stale_after_seconds,
        }
    age = max(0.0, (now - int(last_event_ts_ms)) / 1000.0)
    if age <= heartbeat_interval_seconds * 1.5:
        band = "fresh"
        stale = False
        needs_reconnect = False
    elif age <= stale_after_seconds:
        band = "aging"
        stale = False
        needs_reconnect = False
    else:
        band = "stale"
        stale = True
        needs_reconnect = True
    return {
        "band": band,
        "age_seconds": age,
        "stale": stale,
        "needs_reconnect": needs_reconnect,
        "heartbeat_interval_seconds": heartbeat_interval_seconds,
        "stale_after_seconds": stale_after_seconds,
    }
