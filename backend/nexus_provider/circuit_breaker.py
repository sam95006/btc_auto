"""Provider-specific circuit breaker with open/half-open recovery."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderCircuitBreaker:
    """Trip on repeated transport failures; recover after cooldown."""

    failure_threshold: int = 3
    cooldown_seconds: float = 60.0
    half_open_successes_needed: int = 1
    _failures: dict[str, int] = field(default_factory=dict)
    _open_until: dict[str, float] = field(default_factory=dict)
    _half_open: dict[str, bool] = field(default_factory=dict)
    _half_open_successes: dict[str, int] = field(default_factory=dict)
    _trip_count: dict[str, int] = field(default_factory=dict)

    def is_open(self, provider: str, *, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        until = self._open_until.get(provider, 0.0)
        if until <= 0:
            return False
        if now < until:
            return True
        # Cooldown elapsed → half-open probe window
        self._half_open[provider] = True
        self._open_until[provider] = 0.0
        return False

    def is_half_open(self, provider: str) -> bool:
        return bool(self._half_open.get(provider))

    def record_success(self, provider: str) -> None:
        if self._half_open.get(provider):
            n = int(self._half_open_successes.get(provider) or 0) + 1
            self._half_open_successes[provider] = n
            if n >= self.half_open_successes_needed:
                self._half_open[provider] = False
                self._half_open_successes[provider] = 0
                self._failures[provider] = 0
                self._open_until[provider] = 0.0
            return
        self._failures[provider] = 0

    def record_failure(
        self,
        provider: str,
        *,
        cooldown_seconds: float | None = None,
        now: float | None = None,
    ) -> bool:
        """Record failure; returns True if breaker just tripped open."""
        now = time.monotonic() if now is None else now
        if self._half_open.get(provider):
            self._half_open[provider] = False
            self._half_open_successes[provider] = 0
            cd = float(cooldown_seconds if cooldown_seconds is not None else self.cooldown_seconds)
            self._open_until[provider] = now + max(1.0, cd)
            self._trip_count[provider] = int(self._trip_count.get(provider) or 0) + 1
            self._failures[provider] = self.failure_threshold
            return True
        n = int(self._failures.get(provider) or 0) + 1
        self._failures[provider] = n
        if n >= self.failure_threshold:
            cd = float(cooldown_seconds if cooldown_seconds is not None else self.cooldown_seconds)
            self._open_until[provider] = now + max(1.0, cd)
            self._trip_count[provider] = int(self._trip_count.get(provider) or 0) + 1
            return True
        return False

    def trip(self, provider: str, *, seconds: float | None = None, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        cd = float(seconds if seconds is not None else self.cooldown_seconds)
        self._open_until[provider] = now + max(1.0, cd)
        self._failures[provider] = self.failure_threshold
        self._half_open[provider] = False
        self._trip_count[provider] = int(self._trip_count.get(provider) or 0) + 1

    def record_rate_limit(
        self,
        provider: str,
        *,
        cooldown_seconds: float | None = None,
        now: float | None = None,
    ) -> None:
        """HTTP 429 / RATE_LIMITED opens the breaker immediately (capacity isolation)."""
        self.trip(provider, seconds=cooldown_seconds, now=now)

    def status(self, provider: str, *, now: float | None = None) -> dict[str, Any]:
        now = time.monotonic() if now is None else now
        open_ = self.is_open(provider, now=now)
        return {
            "provider": provider,
            "state": (
                "OPEN"
                if open_
                else ("HALF_OPEN" if self.is_half_open(provider) else "CLOSED")
            ),
            "failures": int(self._failures.get(provider) or 0),
            "trip_count": int(self._trip_count.get(provider) or 0),
            "open_remaining_s": max(0.0, float(self._open_until.get(provider) or 0.0) - now),
        }
