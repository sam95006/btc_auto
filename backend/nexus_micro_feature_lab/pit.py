"""Point-in-time eligibility and observation envelope helpers."""
from __future__ import annotations

from typing import Any, Iterable

from backend.nexus_micro_feature_lab.constants import (
    DEFAULT_STALE_AFTER_MS,
    FEATURE_SCHEMA_VERSION,
)
from backend.nexus_micro_feature_lab.catalog import require_feature


def event_eligible(event: dict[str, Any], *, as_of_ms: int) -> bool:
    """PIT rule: both exchange and receive timestamps must be <= as_of_ms."""
    ex = int(event.get("exchange_timestamp") or 0)
    rx = int(event.get("receive_timestamp") or 0)
    if ex <= 0 or rx <= 0:
        return False
    return ex <= as_of_ms and rx <= as_of_ms


def filter_pit(events: Iterable[dict[str, Any]], *, as_of_ms: int) -> list[dict[str, Any]]:
    return [e for e in events if event_eligible(e, as_of_ms=as_of_ms)]


def in_window(event: dict[str, Any], *, window_start_ms: int, window_end_ms: int) -> bool:
    ts = int(event.get("exchange_timestamp") or 0)
    return window_start_ms <= ts < window_end_ms


def select_window_pit(
    events: Iterable[dict[str, Any]],
    *,
    window_start_ms: int,
    window_end_ms: int,
    as_of_ms: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Returns (eligible_in_window, not_yet_available_in_window)."""
    eligible: list[dict[str, Any]] = []
    not_yet: list[dict[str, Any]] = []
    for e in events:
        if not in_window(e, window_start_ms=window_start_ms, window_end_ms=window_end_ms):
            continue
        ex = int(e.get("exchange_timestamp") or 0)
        rx = int(e.get("receive_timestamp") or 0)
        if ex <= 0:
            continue
        if ex <= as_of_ms and rx <= as_of_ms:
            eligible.append(e)
        elif ex <= as_of_ms and rx > as_of_ms:
            not_yet.append(e)
    return eligible, not_yet


def observation(
    *,
    feature_id: str,
    symbol: str,
    window_start_ms: int,
    window_end_ms: int,
    as_of_ms: int,
    value: Any,
    availability: str,
    source_events: list[dict[str, Any]],
    extras: dict[str, Any] | None = None,
    stale_after_ms: int = DEFAULT_STALE_AFTER_MS,
) -> dict[str, Any]:
    meta = require_feature(feature_id)
    if source_events:
        event_ts = max(int(e["exchange_timestamp"]) for e in source_events)
        available_at = max(int(e["receive_timestamp"]) for e in source_events)
    else:
        event_ts = None
        available_at = None
    staleness_ms = None
    stale = False
    if available_at is not None:
        staleness_ms = max(0, int(as_of_ms) - int(available_at))
        stale = staleness_ms > stale_after_ms
    missing_reason = None
    if availability == "MISSING":
        missing_reason = "no_eligible_events_in_window"
    elif availability == "NOT_YET_AVAILABLE":
        missing_reason = "events_exist_but_receive_after_as_of"
    elif availability == "PARTIAL":
        missing_reason = "insufficient_or_degenerate_inputs"
    out: dict[str, Any] = {
        "schema": "v13_e_feature_observation",
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_id": feature_id,
        "definition": meta["definition"],
        "units": meta["units"],
        "symbol": symbol,
        "window_start_ms": window_start_ms,
        "window_end_ms": window_end_ms,
        "as_of_ms": as_of_ms,
        "event_timestamp_ms": event_ts,
        "available_at_ms": available_at,
        "availability": availability,
        "missing_reason": missing_reason,
        "staleness_ms": staleness_ms,
        "stale": stale,
        "stale_after_ms": stale_after_ms,
        "value": value,
        "source_event_count": len(source_events),
        "predictive_edge_claimed": False,
        "strategy_signal": False,
    }
    if extras:
        out["extras"] = extras
    return out
