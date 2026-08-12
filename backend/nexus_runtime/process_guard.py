"""Runtime guard: no simulated session may attempt an exchange-write call.

Any code path that would otherwise attempt a real exchange write must raise
``ExchangeWriteAttemptError`` so the orchestrator can flag the session as
FAILED_SAFE. The orchestrator instruments this counter — production
exchange clients are never constructed in simulated sessions.
"""
from __future__ import annotations

import threading
from typing import Any


class ExchangeWriteAttemptError(RuntimeError):
    """Raised when a session attempts to write to a real exchange endpoint."""


class NoExchangeWriteGuard:
    """Counts and blocks accidental exchange-write attempts inside a session."""

    def __init__(self) -> None:
        self._count = 0
        self._details: list[str] = []
        self._lock = threading.Lock()

    def attempt(self, endpoint: str, *, detail: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._count += 1
            self._details.append(str(endpoint))
        raise ExchangeWriteAttemptError(
            f"blocked_exchange_write_attempt:{endpoint}"
        )

    @property
    def exchange_write_attempt_count(self) -> int:
        with self._lock:
            return self._count

    def report(self) -> dict[str, Any]:
        with self._lock:
            return {
                "exchange_write_attempt_count": self._count,
                "attempted_endpoints": list(self._details),
            }


def assert_no_exchange_write(count: int) -> None:
    """Invariant assertion for tests / runners."""
    if count != 0:
        raise ExchangeWriteAttemptError(f"exchange_write_attempts_detected:{count}")
