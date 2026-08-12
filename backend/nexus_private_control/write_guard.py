"""No-exchange-write guard for the Founder-private control plane."""
from __future__ import annotations

import threading
from typing import Any


class ExchangeWriteForbidden(RuntimeError):
    """Raised on any exchange-write attempt. Fail-closed."""


class NoExchangeWriteGuard:
    """Counts and blocks accidental exchange writes inside the control plane."""

    def __init__(self) -> None:
        self._count = 0
        self._details: list[str] = []
        self._lock = threading.Lock()

    def attempt(self, endpoint: str, *, detail: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._count += 1
            self._details.append(str(endpoint))
        raise ExchangeWriteForbidden(f"blocked_exchange_write_attempt:{endpoint}")

    @property
    def exchange_write_attempt_count(self) -> int:
        with self._lock:
            return self._count

    def report(self) -> dict[str, Any]:
        with self._lock:
            return {
                "exchange_write_attempt_count": self._count,
                "attempted_endpoints": list(self._details),
                "exchange_writes_permitted": False,
            }
