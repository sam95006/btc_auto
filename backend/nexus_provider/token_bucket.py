"""Bounded token-bucket rate scheduler (provider-local)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    """Simple token bucket. capacity == burst; refill_rate tokens per second."""

    capacity: float
    refill_rate: float
    tokens: float = field(init=False)
    updated_at: float = field(init=False)

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("capacity must be > 0")
        if self.refill_rate <= 0:
            raise ValueError("refill_rate must be > 0")
        self.tokens = float(self.capacity)
        self.updated_at = time.monotonic()

    def _refill(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        elapsed = max(0.0, now - self.updated_at)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.updated_at = now

    def try_acquire(self, cost: float = 1.0, *, now: float | None = None) -> bool:
        if cost <= 0:
            return True
        self._refill(now)
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def time_until_available(self, cost: float = 1.0, *, now: float | None = None) -> float:
        if cost <= 0:
            return 0.0
        self._refill(now)
        if self.tokens >= cost:
            return 0.0
        missing = cost - self.tokens
        return missing / self.refill_rate

    def snapshot(self) -> dict[str, float]:
        self._refill()
        return {
            "capacity": float(self.capacity),
            "refill_rate": float(self.refill_rate),
            "tokens": float(self.tokens),
        }
