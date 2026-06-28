"""Shared LLM rate-limit gate for Stage 4 (health check + decisions)."""
from __future__ import annotations

import os
import time
from typing import Optional


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

    def seconds_until_ready(self) -> float:
        now = time.monotonic()
        wait_backoff = max(0.0, self._backoff_until - now)
        min_gap = self.min_interval_seconds()
        wait_gap = max(0.0, min_gap - (now - self._last_call_at)) if self._last_call_at else 0.0
        return max(wait_backoff, wait_gap)

    def acquire(self) -> bool:
        """Return True if an LLM call may proceed now."""
        if self.in_backoff():
            return False
        min_gap = self.min_interval_seconds()
        if self._last_call_at and (time.monotonic() - self._last_call_at) < min_gap:
            return False
        return True

    def record_call_start(self) -> None:
        self._last_call_at = time.monotonic()

    def record_rate_limit(self, *, backoff_seconds: float | None = None) -> None:
        backoff = backoff_seconds if backoff_seconds is not None else self.backoff_seconds_on_429()
        self._backoff_until = time.monotonic() + backoff

    def record_success(self) -> None:
        self._last_call_at = time.monotonic()
