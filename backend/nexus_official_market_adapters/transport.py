"""Bounded HTTP transport — timeout, retry, rate-limit, circuit breaker."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from backend.nexus_official_market_adapters.constitution import (
    OfficialReadOnlyConstitution,
    PublicMarketBoundaryError,
)
from backend.nexus_official_market_adapters.constants import (
    DEFAULT_BACKOFF_BASE_SECONDS,
    DEFAULT_CIRCUIT_FAILURE_THRESHOLD,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RATE_LIMIT_PER_SECOND,
    DEFAULT_TIMEOUT_SECONDS,
)


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
    failure_threshold: int = DEFAULT_CIRCUIT_FAILURE_THRESHOLD
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
class TokenBucketRateLimiter:
    """Simple client-side rate limiter — never bypassed."""

    rate_per_second: float = DEFAULT_RATE_LIMIT_PER_SECOND
    tokens: float = field(init=False)
    updated_at: float = field(init=False)
    wait_count: int = 0

    def __post_init__(self) -> None:
        self.tokens = float(self.rate_per_second)
        self.updated_at = time.monotonic()

    def acquire(self) -> None:
        while True:
            now = time.monotonic()
            elapsed = now - self.updated_at
            self.updated_at = now
            self.tokens = min(self.rate_per_second, self.tokens + elapsed * self.rate_per_second)
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            self.wait_count += 1
            # Honest wait — do not bypass rate limits.
            time.sleep(max(0.01, (1.0 - self.tokens) / self.rate_per_second))


@dataclass
class BoundedHttpClient:
    constitution: OfficialReadOnlyConstitution
    transport: HttpTransport | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS
    rate_limiter: TokenBucketRateLimiter = field(default_factory=TokenBucketRateLimiter)
    circuit_breaker: CircuitBreakerState = field(default_factory=CircuitBreakerState)
    request_count: int = 0
    success_count: int = 0

    def get(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("GET", url, params=params, headers=None)

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
        transport = self.transport or default_urllib_transport
        last_exc: Exception | None = None

        for attempt in range(self.max_retries):
            self.rate_limiter.acquire()
            self.request_count += 1
            try:
                result = transport(
                    method.upper(),
                    url,
                    params=params or {},
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                if result.get("ok") is False and result.get("retryable"):
                    raise RuntimeError(str(result.get("error") or "retryable_failure"))
                if result.get("ok") is False:
                    raise RuntimeError(str(result.get("error") or "http_failure"))
                self.success_count += 1
                self.circuit_breaker.record_success()
                return result
            except PublicMarketBoundaryError:
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
            "rate_limit_waits": self.rate_limiter.wait_count,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
        }


def default_urllib_transport(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """stdlib-only GET transport for optional live smoke (no third-party deps)."""
    if method.upper() != "GET":
        return {"ok": False, "error": "only_GET_supported", "retryable": False}
    query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
    full = f"{url}?{query}" if query else url
    req = urllib.request.Request(full, method="GET", headers=dict(headers or {}))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                return {"ok": False, "error": "invalid_json", "retryable": False, "status": resp.status}
            return {"ok": True, "status": resp.status, "json": parsed, "headers": dict(resp.headers)}
    except urllib.error.HTTPError as exc:
        retryable = exc.code in {408, 425, 429, 500, 502, 503, 504}
        return {"ok": False, "error": f"http_{exc.code}", "retryable": retryable, "status": exc.code}
    except Exception as exc:  # noqa: BLE001 — surface as transport result
        return {"ok": False, "error": type(exc).__name__, "retryable": True}


FixtureLoader = Callable[[str], dict[str, Any]]


__all__ = [
    "BoundedHttpClient",
    "CircuitBreakerState",
    "TokenBucketRateLimiter",
    "HttpTransport",
    "default_urllib_transport",
]
