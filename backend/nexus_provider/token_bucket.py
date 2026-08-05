"""Bounded token-bucket rate scheduler (provider-local values; shared algorithm)."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TokenBucket:
    """Token bucket. capacity == burst; refill_rate/refill_per_s tokens per second.

    ``refill_rate`` / ``refill_per_s`` of 0 means no refill (test / hard-stop).
    Provider-specific capacity/refill VALUES may differ; algorithm does not.
    """

    capacity: float = 5.0
    refill_rate: float | None = None
    refill_per_s: float | None = None
    tokens: float | None = None
    updated_at: float = field(default_factory=time.monotonic)
    profile_id: str = ""

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("capacity must be > 0")
        rate = self.refill_rate if self.refill_rate is not None else self.refill_per_s
        if rate is None:
            rate = 0.2
        if rate < 0:
            raise ValueError("refill_rate must be >= 0")
        self.refill_rate = float(rate)
        self.refill_per_s = float(rate)
        if self.tokens is None:
            self.tokens = float(self.capacity)
        else:
            self.tokens = float(self.tokens)

    def _refill(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        elapsed = max(0.0, now - self.updated_at)
        rate = float(self.refill_rate or 0.0)
        self.tokens = min(self.capacity, float(self.tokens or 0.0) + elapsed * rate)
        self.updated_at = now

    def try_acquire(self, cost: float = 1.0, *, now: float | None = None) -> bool:
        if cost <= 0:
            return True
        self._refill(now)
        if float(self.tokens or 0.0) >= cost:
            self.tokens = float(self.tokens or 0.0) - cost
            return True
        return False

    def time_until_available(self, cost: float = 1.0, *, now: float | None = None) -> float:
        if cost <= 0:
            return 0.0
        self._refill(now)
        if float(self.tokens or 0.0) >= cost:
            return 0.0
        missing = cost - float(self.tokens or 0.0)
        rate = float(self.refill_rate or 0.0)
        if rate <= 0:
            return math.inf
        return missing / rate

    def snapshot(self) -> dict[str, float]:
        self._refill()
        return {
            "capacity": float(self.capacity),
            "refill_rate": float(self.refill_rate or 0.0),
            "tokens": float(self.tokens or 0.0),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "capacity": self.capacity,
            "refill_per_s": float(self.refill_per_s or 0.0),
            "tokens": round(float(self.tokens or 0.0), 4),
        }
