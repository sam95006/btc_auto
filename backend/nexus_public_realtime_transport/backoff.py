"""Reconnect backoff helpers for public realtime clients."""
from __future__ import annotations

import random
from dataclasses import dataclass

from backend.nexus_public_realtime_transport.constants import (
    BACKOFF_INITIAL_SECONDS,
    BACKOFF_JITTER_RATIO,
    BACKOFF_MAX_SECONDS,
    BACKOFF_MULTIPLIER,
)


@dataclass
class BackoffState:
    attempt: int = 0
    current_seconds: float = BACKOFF_INITIAL_SECONDS

    def next_delay(self, *, rng: random.Random | None = None) -> float:
        """Return delay for the current attempt, then advance."""
        base = min(BACKOFF_MAX_SECONDS, BACKOFF_INITIAL_SECONDS * (BACKOFF_MULTIPLIER ** self.attempt))
        jitter_src = rng or random
        jitter = base * BACKOFF_JITTER_RATIO * jitter_src.random()
        delay = min(BACKOFF_MAX_SECONDS, base + jitter)
        self.attempt += 1
        self.current_seconds = delay
        return delay

    def reset(self) -> None:
        self.attempt = 0
        self.current_seconds = BACKOFF_INITIAL_SECONDS
