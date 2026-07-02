"""Absolute tick scheduling for Stage 4 dry-run loops."""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List


def compute_expected_tick_count(duration_minutes: float, poll_interval_seconds: float) -> int:
    if poll_interval_seconds <= 0 or duration_minutes <= 0.05:
        return 1
    total_seconds = duration_minutes * 60.0
    return max(1, int(math.floor(total_seconds / poll_interval_seconds)))


def scheduled_tick_start(
    started_at: float,
    tick_index: int,
    poll_interval_seconds: float,
) -> float:
    return started_at + (tick_index - 1) * poll_interval_seconds


def wait_until_scheduled_tick(
    started_at: float,
    tick_index: int,
    poll_interval_seconds: float,
) -> float:
    """Sleep until the scheduled tick start. Returns drift seconds (late start)."""
    target = scheduled_tick_start(started_at, tick_index, poll_interval_seconds)
    now = time.time()
    drift = max(0.0, now - target)
    if now < target:
        time.sleep(target - now)
    return drift


class TickSchedulerMetrics:
    def __init__(self) -> None:
        self.drift_seconds: List[float] = []
        self.processing_seconds: List[float] = []

    def record_tick(self, *, processing_seconds: float, drift_seconds: float) -> None:
        self.processing_seconds.append(max(0.0, processing_seconds))
        self.drift_seconds.append(max(0.0, drift_seconds))

    def summary_fields(
        self,
        *,
        expected_tick_count: int,
        actual_tick_count: int,
    ) -> Dict[str, Any]:
        proc = self.processing_seconds
        drifts = self.drift_seconds
        return {
            "expected_tick_count": expected_tick_count,
            "actual_tick_count": actual_tick_count,
            "tick_count": actual_tick_count,
            "tick_drift_seconds_max": round(max(drifts), 3) if drifts else 0.0,
            "tick_processing_seconds_avg": round(sum(proc) / len(proc), 3) if proc else 0.0,
            "tick_processing_seconds_max": round(max(proc), 3) if proc else 0.0,
        }


__all__ = [
    "TickSchedulerMetrics",
    "compute_expected_tick_count",
    "scheduled_tick_start",
    "wait_until_scheduled_tick",
]
