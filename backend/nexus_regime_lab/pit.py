"""Point-in-time eligibility helpers for regime / lead-lag observations."""
from __future__ import annotations

from typing import Any, Iterable

from backend.nexus_regime_lab.constants import DEFAULT_STALE_AFTER_MS, REGIME_SCHEMA_VERSION
from backend.nexus_regime_lab.catalog import require_regime


def bar_eligible(bar: dict[str, Any], *, as_of_ms: int) -> bool:
    """PIT rule: both exchange and receive timestamps must be <= as_of_ms."""
    ex = int(bar.get("exchange_timestamp") or 0)
    rx = int(bar.get("receive_timestamp") or 0)
    if ex <= 0 or rx <= 0:
        return False
    return ex <= as_of_ms and rx <= as_of_ms


def filter_pit(bars: Iterable[dict[str, Any]], *, as_of_ms: int) -> list[dict[str, Any]]:
    return [b for b in bars if bar_eligible(b, as_of_ms=as_of_ms)]


def filter_pit_lookback(
    bars: Iterable[dict[str, Any]],
    *,
    as_of_ms: int,
    lookback_start_ms: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Returns (eligible_in_lookback, not_yet_available_in_lookback)."""
    eligible: list[dict[str, Any]] = []
    not_yet: list[dict[str, Any]] = []
    for b in bars:
        ex = int(b.get("exchange_timestamp") or 0)
        rx = int(b.get("receive_timestamp") or 0)
        if ex <= 0:
            continue
        if not (lookback_start_ms <= ex <= as_of_ms):
            continue
        if rx <= as_of_ms:
            eligible.append(b)
        else:
            not_yet.append(b)
    eligible.sort(key=lambda x: int(x["exchange_timestamp"]))
    not_yet.sort(key=lambda x: int(x["exchange_timestamp"]))
    return eligible, not_yet


def observation(
    *,
    regime_id: str,
    symbol: str,
    lookback_start_ms: int,
    lookback_end_ms: int,
    as_of_ms: int,
    label: Any,
    metrics: dict[str, Any] | None,
    availability: str,
    source_bars: list[dict[str, Any]],
    extras: dict[str, Any] | None = None,
    stale_after_ms: int = DEFAULT_STALE_AFTER_MS,
) -> dict[str, Any]:
    meta = require_regime(regime_id)
    if source_bars:
        event_ts = max(int(b["exchange_timestamp"]) for b in source_bars)
        available_at = max(int(b["receive_timestamp"]) for b in source_bars)
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
        missing_reason = "no_eligible_bars_in_lookback"
    elif availability == "NOT_YET_AVAILABLE":
        missing_reason = "bars_exist_but_receive_after_as_of"
    elif availability == "PARTIAL":
        missing_reason = "insufficient_or_degenerate_inputs"
    out: dict[str, Any] = {
        "schema": "v14_f_regime_observation",
        "regime_schema_version": REGIME_SCHEMA_VERSION,
        "regime_id": regime_id,
        "definition": meta["definition"],
        "units": meta["units"],
        "symbol": symbol,
        "lookback_start_ms": lookback_start_ms,
        "lookback_end_ms": lookback_end_ms,
        "as_of_ms": as_of_ms,
        "event_timestamp_ms": event_ts,
        "available_at_ms": available_at,
        "availability": availability,
        "missing_reason": missing_reason,
        "staleness_ms": staleness_ms,
        "stale": stale,
        "stale_after_ms": stale_after_ms,
        "label": label,
        "metrics": metrics,
        "source_bar_count": len(source_bars),
        "predictive_edge_claimed": False,
        "strategy_signal": False,
        "contemporaneous_only": True,
    }
    if extras:
        out["extras"] = extras
    return out
