"""Rate-limit pause controller for read-only ingest."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_incremental_backfill_live_ingest.hashing import utc_now_iso


@dataclass
class RateLimitController:
    """Pause ingest when provider weight / 429 signals fire. No exchange write."""

    max_weight: int = 1200
    used_weight: int = 0
    paused: bool = False
    pause_reason: str | None = None
    pause_events: list[dict[str, Any]] = field(default_factory=list)

    def record_weight(self, weight: int) -> None:
        self.used_weight += int(weight)
        if self.used_weight >= self.max_weight:
            self.pause(reason="weight_budget_exhausted")

    def observe_http_status(self, status: int) -> None:
        if int(status) == 429:
            self.pause(reason="http_429")

    def pause(self, *, reason: str) -> None:
        self.paused = True
        self.pause_reason = reason
        self.pause_events.append({"at": utc_now_iso(), "reason": reason})

    def resume(self) -> None:
        self.paused = False
        self.pause_reason = None
        self.used_weight = 0

    def assert_not_paused(self) -> None:
        if self.paused:
            raise RuntimeError(f"rate_limit_paused:{self.pause_reason}")

    def snapshot(self) -> dict[str, Any]:
        return {
            "max_weight": self.max_weight,
            "used_weight": self.used_weight,
            "paused": self.paused,
            "pause_reason": self.pause_reason,
            "pause_event_count": len(self.pause_events),
        }
