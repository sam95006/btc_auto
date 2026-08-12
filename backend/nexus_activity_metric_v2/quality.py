"""Activity quality state machine.

Partial warmup → INSUFFICIENT_HISTORY (never emit fabricated zero as LIVE).
"""
from __future__ import annotations

from typing import Any

from backend.nexus_activity_metric_v2.constants import (
    DEFAULT_STALE_MS,
    DEFAULT_WINDOW_MS,
)


def evaluate_quality_state(
    *,
    coverage_start_ms: int | None,
    coverage_end_ms: int | None,
    now_ms: int,
    window_ms: int = DEFAULT_WINDOW_MS,
    stale_ms: int = DEFAULT_STALE_MS,
    last_event_time_ms: int | None,
    last_receive_time_ms: int | None,
    unique_trade_count: int,
    provider_available: bool = True,
    provider_degraded: bool = False,
    rate_limited: bool = False,
) -> tuple[str, bool, dict[str, Any]]:
    """Return (quality_state, warmup_complete, detail)."""
    detail: dict[str, Any] = {}

    if not provider_available:
        return "UNAVAILABLE", False, {"reason": "provider_unavailable"}

    if coverage_start_ms is None or coverage_end_ms is None:
        return "UNAVAILABLE", False, {"reason": "no_coverage"}

    span_ms = max(0, int(coverage_end_ms) - int(coverage_start_ms))
    detail["coverage_span_ms"] = span_ms
    detail["window_ms"] = int(window_ms)

    # Warmup: need contiguous coverage spanning ~full window.
    warmup_complete = span_ms >= int(window_ms) * 0.98
    detail["warmup_complete"] = warmup_complete

    ref_event = last_event_time_ms if last_event_time_ms is not None else coverage_end_ms
    ref_recv = last_receive_time_ms if last_receive_time_ms is not None else now_ms
    freshness = max(0, int(now_ms) - int(ref_recv))
    detail["freshness_ms"] = freshness
    detail["unique_trade_count"] = int(unique_trade_count)

    if rate_limited or provider_degraded:
        # Still report metrics, but mark degraded.
        if not warmup_complete:
            return "INSUFFICIENT_HISTORY", False, {**detail, "reason": "warmup_and_degraded"}
        return "DEGRADED", True, {**detail, "reason": "provider_degraded_or_rate_limited"}

    if freshness > int(stale_ms):
        if not warmup_complete:
            return "INSUFFICIENT_HISTORY", False, {**detail, "reason": "stale_during_warmup"}
        return "STALE", True, {**detail, "reason": "freshness_exceeded"}

    if not warmup_complete:
        # Critical: partial history is NOT LIVE and NOT a zero trade_count claim.
        return "INSUFFICIENT_HISTORY", False, {**detail, "reason": "partial_warmup"}

    if unique_trade_count <= 0:
        # Warmup span met but empty — treat as degraded (market silent / feed gap).
        return "DEGRADED", True, {**detail, "reason": "empty_after_warmup"}

    _ = ref_event  # retained for clock-skew audits by callers
    return "LIVE", True, {**detail, "reason": "ok"}
