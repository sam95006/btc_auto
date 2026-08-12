"""Deterministic accelerated logical clock for Session Orchestrator V1.1.

The clock is entirely internal — it never reads from the system time source
during a run. It supports:

  * ``advance(seconds=...)`` — advance forward by a strictly positive amount.
  * ``advance_hours(hours)`` — convenience.
  * ``jump_forward(seconds)`` — inject forward clock jump (fault injection).
  * ``jump_backward(seconds)`` — inject backward clock jump. This is
    considered a fault and must fail-closed when applied to non-monotonic
    critical points (checkpoints/ledger sequencing) at the orchestrator level.

The clock returns UTC ISO-8601 timestamps derived from ``epoch_start`` plus
accumulated logical seconds; the wall-clock elapsed time of the actual
process is *not* used for ordering.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone


class ClockError(Exception):
    """Raised when an invalid clock operation is attempted."""


def now_utc_iso() -> str:
    """Return current process wall clock in UTC ISO-8601 (for wall timing only)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class AcceleratedLogicalClock:
    """Thread-safe, deterministic accelerated logical clock.

    Notes on semantics:
      * ``current_logical_seconds`` is monotonic under normal ``advance()``.
      * ``jump_backward()`` DECREASES logical time — orchestrator code that
        depends on monotonicity must detect this via
        ``last_monotonic_violation`` and route to RECOVERING / BLOCKED.
    """

    def __init__(self, *, epoch_start: datetime | None = None) -> None:
        self._epoch_start = (epoch_start or datetime(2026, 1, 1, tzinfo=timezone.utc))
        if self._epoch_start.tzinfo is None:
            self._epoch_start = self._epoch_start.replace(tzinfo=timezone.utc)
        self._elapsed_seconds: float = 0.0
        self._monotonic_seconds: float = 0.0
        self._advance_count: int = 0
        self._forward_jump_count: int = 0
        self._backward_jump_count: int = 0
        self._last_monotonic_violation: str | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @property
    def logical_seconds(self) -> float:
        with self._lock:
            return self._elapsed_seconds

    @property
    def logical_hours(self) -> float:
        return self.logical_seconds / 3600.0

    def now(self) -> datetime:
        with self._lock:
            return self._epoch_start + timedelta(seconds=self._elapsed_seconds)

    def now_iso(self) -> str:
        return self.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    @property
    def last_monotonic_violation(self) -> str | None:
        with self._lock:
            return self._last_monotonic_violation

    @property
    def stats(self) -> dict[str, float | int | str | None]:
        with self._lock:
            return {
                "logical_seconds": self._elapsed_seconds,
                "logical_hours": self._elapsed_seconds / 3600.0,
                "advance_count": self._advance_count,
                "forward_jump_count": self._forward_jump_count,
                "backward_jump_count": self._backward_jump_count,
                "last_monotonic_violation": self._last_monotonic_violation,
                "epoch_start_iso": self._epoch_start.isoformat(),
            }

    # ------------------------------------------------------------------
    # Mutate
    # ------------------------------------------------------------------

    def advance(self, *, seconds: float) -> None:
        if seconds <= 0:
            raise ClockError(f"advance_requires_positive_seconds:{seconds}")
        with self._lock:
            self._elapsed_seconds += float(seconds)
            self._monotonic_seconds += float(seconds)
            self._advance_count += 1

    def advance_hours(self, hours: float) -> None:
        self.advance(seconds=float(hours) * 3600.0)

    def jump_forward(self, seconds: float) -> None:
        if seconds <= 0:
            raise ClockError(f"jump_forward_requires_positive:{seconds}")
        with self._lock:
            self._elapsed_seconds += float(seconds)
            self._monotonic_seconds += float(seconds)
            self._forward_jump_count += 1

    def jump_backward(self, seconds: float) -> None:
        if seconds <= 0:
            raise ClockError(f"jump_backward_requires_positive:{seconds}")
        with self._lock:
            self._elapsed_seconds -= float(seconds)
            # Monotonic anchor is preserved — this is a *violation* signal.
            self._backward_jump_count += 1
            self._last_monotonic_violation = f"backward_jump_{seconds}s"

    def clear_monotonic_violation(self) -> None:
        """Clear the last-monotonic-violation marker after it has been handled.

        Callers must ensure they have already routed the session into
        RECOVERING / BLOCKED before clearing.
        """
        with self._lock:
            self._last_monotonic_violation = None
