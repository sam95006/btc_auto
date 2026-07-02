"""Absolute tick scheduling helpers for Stage 4 dry-run loops."""
from __future__ import annotations

import time
from typing import Any, Dict


def expected_tick_count(duration_minutes: float, poll_interval_seconds: float) -> int:
    """How many ticks fit in duration when scheduled at fixed poll intervals."""
    if duration_minutes <= 0:
        return 1
    if poll_interval_seconds <= 0:
        return 1
    total_seconds = duration_minutes * 60.0
    return max(1, int(total_seconds // poll_interval_seconds))


def seconds_until_next_tick(
    *,
    run_started_at: float,
    tick_index: int,
    poll_interval_seconds: float,
) -> float:
    """Sleep duration to align tick (tick_index+1) at run_started_at + tick_index * poll."""
    if poll_interval_seconds <= 0:
        return 0.0
    next_tick_at = run_started_at + tick_index * poll_interval_seconds
    return max(0.0, next_tick_at - time.time())


def build_tick_scheduler_metrics(
    *,
    duration_minutes: float,
    poll_interval_seconds: float,
    actual_tick_count: int,
    tick_processing_seconds: list[float],
    tick_drift_seconds: list[float],
) -> Dict[str, Any]:
    expected = expected_tick_count(duration_minutes, poll_interval_seconds)
    processing = [float(v) for v in tick_processing_seconds if v >= 0]
    drift = [float(v) for v in tick_drift_seconds if v >= 0]
    return {
        "expected_tick_count": expected,
        "actual_tick_count": int(actual_tick_count),
        "tick_count": int(actual_tick_count),
        "tick_drift_seconds_max": round(max(drift), 3) if drift else 0.0,
        "tick_processing_seconds_avg": round(sum(processing) / len(processing), 3) if processing else 0.0,
        "tick_processing_seconds_max": round(max(processing), 3) if processing else 0.0,
    }


__all__ = [
    "build_tick_scheduler_metrics",
    "expected_tick_count",
    "seconds_until_next_tick",
]
