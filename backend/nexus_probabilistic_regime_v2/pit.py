"""Point-in-time eligibility and freshness helpers for regime V2."""
from __future__ import annotations

from typing import Any, Iterable

from backend.nexus_probabilistic_regime_v2.constants import DEFAULT_STALE_AFTER_MS


def bar_eligible(bar: dict[str, Any], *, as_of_ms: int) -> bool:
    """PIT: both exchange and receive timestamps must be <= as_of_ms."""
    try:
        ex = int(bar.get("exchange_timestamp") or 0)
        rx = int(bar.get("receive_timestamp") or 0)
    except (TypeError, ValueError):
        return False
    if ex <= 0 or rx <= 0:
        return False
    return ex <= as_of_ms and rx <= as_of_ms


def filter_pit(bars: Iterable[dict[str, Any]], *, as_of_ms: int) -> list[dict[str, Any]]:
    out = [b for b in bars if bar_eligible(b, as_of_ms=as_of_ms)]
    out.sort(key=lambda x: int(x["exchange_timestamp"]))
    return out


def filter_pit_lookback(
    bars: Iterable[dict[str, Any]],
    *,
    as_of_ms: int,
    lookback_start_ms: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Returns (eligible_in_lookback, future_leak_candidates)."""
    eligible: list[dict[str, Any]] = []
    not_yet: list[dict[str, Any]] = []
    for b in bars:
        try:
            ex = int(b.get("exchange_timestamp") or 0)
            rx = int(b.get("receive_timestamp") or 0)
        except (TypeError, ValueError):
            continue
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


def prove_no_future_leak(
    used_bars: list[dict[str, Any]],
    *,
    as_of_ms: int,
) -> dict[str, Any]:
    leaks = [
        b
        for b in used_bars
        if int(b.get("exchange_timestamp") or 0) > as_of_ms
        or int(b.get("receive_timestamp") or 0) > as_of_ms
    ]
    return {
        "as_of_ms": as_of_ms,
        "used_bar_count": len(used_bars),
        "future_leak_count": len(leaks),
        "pit_clean": len(leaks) == 0,
    }


def freshness_score(
    *,
    as_of_ms: int,
    available_at_ms: int | None,
    stale_after_ms: int = DEFAULT_STALE_AFTER_MS,
) -> tuple[float, bool, int | None]:
    """Return (freshness in [0,1], stale flag, staleness_ms). Fail-closed when unknown."""
    if available_at_ms is None or available_at_ms <= 0:
        return 0.0, True, None
    staleness_ms = max(0, int(as_of_ms) - int(available_at_ms))
    stale = staleness_ms > int(stale_after_ms)
    if stale_after_ms <= 0:
        return 0.0, True, staleness_ms
    fresh = max(0.0, 1.0 - (staleness_ms / float(stale_after_ms)))
    if stale:
        fresh = 0.0
    return fresh, stale, staleness_ms
