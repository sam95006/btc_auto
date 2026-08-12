"""Public HTTP client with constitution guard, retry, backoff, and circuit breaker."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from backend.nexus_real_shadow.constitution import PublicMarketDataConstitution, PublicDataBoundaryError

TransportFn = Callable[[str, str, dict[str, Any], dict[str, Any] | None, float], dict[str, Any]]


class HttpTransport(Protocol):
    def __call__(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        timeout: float = 10.0,
    ) -> dict[str, Any]: ...


@dataclass
class CircuitBreakerState:
    failure_threshold: int = 5
    failures: int = 0
    open: bool = False
    last_failure: str | None = None

    def record_success(self) -> None:
        self.failures = 0
        self.open = False
        self.last_failure = None

    def record_failure(self, reason: str) -> None:
        self.failures += 1
        self.last_failure = reason
        if self.failures >= self.failure_threshold:
            self.open = True


@dataclass
class PublicHttpClient:
    constitution: PublicMarketDataConstitution
    transport: HttpTransport | None = None
    timeout_seconds: float = 10.0
    max_retries: int = 3
    backoff_base_seconds: float = 0.05
    circuit_breaker: CircuitBreakerState = field(default_factory=CircuitBreakerState)
    request_count: int = 0
    success_count: int = 0

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.request("GET", url, params=params, headers=headers)

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.circuit_breaker.open:
            raise RuntimeError(f"circuit_breaker_open:{self.circuit_breaker.last_failure}")

        self.constitution.validate_http_request(method=method, url=url, headers=headers)
        transport = self.transport or _default_transport
        last_exc: Exception | None = None

        for attempt in range(self.max_retries):
            self.request_count += 1
            try:
                result = transport(
                    method.upper(),
                    url,
                    params or {},
                    headers,
                    self.timeout_seconds,
                )
                if result.get("ok") is False and result.get("retryable"):
                    raise RuntimeError(str(result.get("error") or "retryable_failure"))
                self.success_count += 1
                self.circuit_breaker.record_success()
                return result
            except PublicDataBoundaryError:
                raise
            except Exception as exc:
                last_exc = exc
                self.circuit_breaker.record_failure(type(exc).__name__)
                if attempt + 1 < self.max_retries:
                    time.sleep(self.backoff_base_seconds * (2**attempt))

        raise RuntimeError(f"public_http_failed:{last_exc}")

    def stats(self) -> dict[str, Any]:
        return {
            "request_count": self.request_count,
            "success_count": self.success_count,
            "circuit_open": self.circuit_breaker.open,
            "circuit_failures": self.circuit_breaker.failures,
        }


def _default_transport(
    method: str,
    url: str,
    params: dict[str, Any],
    headers: dict[str, Any] | None,
    timeout: float,
) -> dict[str, Any]:
    del method, params, headers, timeout
    return {"ok": False, "error": "no_transport_configured", "retryable": False}
