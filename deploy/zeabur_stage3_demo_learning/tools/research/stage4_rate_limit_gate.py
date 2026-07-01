"""Shared LLM rate-limit gate for Stage 4 (health check + decisions)."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utc_iso_from_monotonic(target_mono: float) -> str:
    if target_mono <= 0:
        return ""
    delta = target_mono - time.monotonic()
    return datetime.fromtimestamp(time.time() + delta, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Stage4LLMRateGate:
    """Token-bucket style gate: min interval between calls + backoff after 429."""

    _shared: Optional["Stage4LLMRateGate"] = None

    def __init__(self) -> None:
        self._last_call_at: float = 0.0
        self._backoff_until: float = 0.0

    @classmethod
    def shared(cls) -> "Stage4LLMRateGate":
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    @classmethod
    def reset_shared(cls) -> None:
        cls._shared = None

    @staticmethod
    def min_interval_seconds() -> float:
        raw = os.environ.get("STAGE4_LLM_MIN_INTERVAL_SECONDS", "30")
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            return 30.0

    @staticmethod
    def backoff_seconds_on_429() -> float:
        raw = os.environ.get("STAGE4_LLM_BACKOFF_SECONDS", "90")
        try:
            return max(30.0, float(raw))
        except (TypeError, ValueError):
            return 90.0

    def in_backoff(self) -> bool:
        return time.monotonic() < self._backoff_until

    def seconds_since_last_call(self) -> float:
        if not self._last_call_at:
            return 0.0
        return max(0.0, time.monotonic() - self._last_call_at)

    def seconds_until_ready(self) -> float:
        now = time.monotonic()
        wait_backoff = max(0.0, self._backoff_until - now)
        min_gap = self.min_interval_seconds()
        wait_gap = max(0.0, min_gap - (now - self._last_call_at)) if self._last_call_at else 0.0
        return max(wait_backoff, wait_gap)

    def block_reason(self) -> str:
        """Why acquire() would fail: backoff_active_skip or local_rate_gate_skip."""
        if self.in_backoff():
            return "backoff_active_skip"
        min_gap = self.min_interval_seconds()
        if self._last_call_at and (time.monotonic() - self._last_call_at) < min_gap:
            return "local_rate_gate_skip"
        return ""

    def acquire(self) -> bool:
        return not self.block_reason()

    def record_call_start(self) -> None:
        self._last_call_at = time.monotonic()

    def record_rate_limit(self, *, backoff_seconds: float | None = None) -> None:
        backoff = backoff_seconds if backoff_seconds is not None else self.backoff_seconds_on_429()
        self._backoff_until = time.monotonic() + backoff

    def record_success(self) -> None:
        self._last_call_at = time.monotonic()

    def status_dict(self) -> Dict[str, Any]:
        return {
            "seconds_since_last_llm_call": round(self.seconds_since_last_call(), 1),
            "required_wait_seconds": round(self.seconds_until_ready(), 1),
            "backoff_until_utc": _utc_iso_from_monotonic(self._backoff_until),
            "in_backoff": self.in_backoff(),
            "block_reason": self.block_reason(),
        }
