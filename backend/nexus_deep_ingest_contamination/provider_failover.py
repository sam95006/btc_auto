"""Provider failover simulator — simplify circuit clock to monotonic counter."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_deep_ingest_contamination.constants import (
    OUTAGE_STATUS,
    PRIMARY_PROVIDER,
    RATE_LIMIT_STATUS,
    SECONDARY_PROVIDER,
)
from backend.nexus_provider.circuit_breaker import ProviderCircuitBreaker
from backend.nexus_provider.retry_policy import (
    compute_resume_wait_s,
    parse_retry_after,
    retries_exhausted,
)
from backend.nexus_provider.token_bucket import TokenBucket


@dataclass
class FixtureTransportResponse:
    provider: str
    status_code: int
    body: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    payload: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status_code": self.status_code,
            "body": self.body,
            "headers": dict(self.headers),
            "payload": self.payload,
        }


@dataclass
class ProviderFailoverSimulator:
    """Deterministic fixture transport with rate-limit + outage failover."""

    primary: str = PRIMARY_PROVIDER
    secondary: str = SECONDARY_PROVIDER
    bucket: TokenBucket = field(default_factory=lambda: TokenBucket(capacity=2.0, refill_rate=0.0))
    breaker: ProviderCircuitBreaker = field(
        default_factory=lambda: ProviderCircuitBreaker(failure_threshold=2, cooldown_seconds=30.0)
    )
    primary_script: list[FixtureTransportResponse] = field(default_factory=list)
    secondary_script: list[FixtureTransportResponse] = field(default_factory=list)
    _primary_i: int = 0
    _secondary_i: int = 0
    _clock: float = 0.0
    call_log: list[dict[str, Any]] = field(default_factory=list)

    def _tick(self) -> float:
        self._clock += 1.0
        return self._clock

    def _next(self, provider: str) -> FixtureTransportResponse:
        if provider == self.primary:
            if self._primary_i >= len(self.primary_script):
                return FixtureTransportResponse(
                    provider=provider, status_code=200, payload={"ok": True}
                )
            resp = self.primary_script[self._primary_i]
            self._primary_i += 1
            return resp
        if self._secondary_i >= len(self.secondary_script):
            return FixtureTransportResponse(provider=provider, status_code=200, payload={"ok": True})
        resp = self.secondary_script[self._secondary_i]
        self._secondary_i += 1
        return resp

    def request(self, *, prefer_primary: bool = True) -> dict[str, Any]:
        order = [self.primary, self.secondary] if prefer_primary else [self.secondary, self.primary]
        last: dict[str, Any] | None = None
        for idx, provider in enumerate(order):
            now = self._tick()
            if self.breaker.is_open(provider, now=now):
                last = {
                    "provider": provider,
                    "status": "CIRCUIT_OPEN",
                    "failover": True,
                }
                self.call_log.append(last)
                continue

            if provider == self.primary and not self.bucket.try_acquire(1.0, now=now):
                wait = compute_resume_wait_s(
                    {"retry-after": "2"},
                    body="rate limited try again in 2 seconds",
                    now=0.0,
                    default_s=2.0,
                )
                self.breaker.record_rate_limit(provider, cooldown_seconds=wait, now=now)
                last = {
                    "provider": provider,
                    "status": "RATE_LIMITED",
                    "status_code": RATE_LIMIT_STATUS,
                    "resume_wait_s": wait,
                    "failover": True,
                }
                self.call_log.append(last)
                continue

            resp = self._next(provider)
            entry = resp.to_dict()
            if resp.status_code == RATE_LIMIT_STATUS:
                wait = parse_retry_after(resp.headers, body=resp.body, now=0.0, default_s=5.0) or 5.0
                self.breaker.record_rate_limit(
                    provider, cooldown_seconds=float(wait), now=now
                )
                entry["status"] = "RATE_LIMITED"
                entry["resume_wait_s"] = wait
                entry["failover"] = True
                self.call_log.append(entry)
                last = entry
                continue
            if resp.status_code >= 500 or resp.status_code == OUTAGE_STATUS:
                tripped = self.breaker.record_failure(provider, now=now)
                entry["status"] = "OUTAGE"
                entry["circuit_tripped"] = tripped
                entry["failover"] = True
                self.call_log.append(entry)
                last = entry
                continue
            self.breaker.record_success(provider)
            entry["status"] = "OK"
            entry["failover"] = idx != 0
            self.call_log.append(entry)
            return entry
        return last or {"status": "ALL_PROVIDERS_FAILED", "failover": True}

    def _reset(self) -> None:
        self._primary_i = 0
        self._secondary_i = 0
        self._clock = 0.0
        self.bucket = TokenBucket(capacity=5.0, refill_rate=0.0)
        self.breaker = ProviderCircuitBreaker(failure_threshold=2, cooldown_seconds=30.0)
        self.call_log.clear()

    def run_rate_limit_failover_scenario(self) -> dict[str, Any]:
        """Primary returns 429 then secondary serves — fixture proof."""
        self.primary_script = [
            FixtureTransportResponse(
                provider=self.primary,
                status_code=RATE_LIMIT_STATUS,
                headers={"retry-after": "10"},
                body="try again in 10 seconds",
            )
        ]
        self.secondary_script = [
            FixtureTransportResponse(
                provider=self.secondary,
                status_code=200,
                payload={"source": self.secondary, "fixture": True},
            )
        ]
        self._reset()
        result = self.request()
        ok = (
            result.get("status") == "OK"
            and result.get("provider") == self.secondary
            and result.get("failover") is True
        )
        return {
            "scenario": "rate_limit_failover",
            "pass": ok,
            "result": result,
            "call_log": list(self.call_log),
            "fixture_only": True,
            "live_network": False,
        }

    def run_outage_failover_scenario(self) -> dict[str, Any]:
        """Primary 503 outage → secondary OK."""
        self.primary_script = [
            FixtureTransportResponse(
                provider=self.primary, status_code=OUTAGE_STATUS, body="unavailable"
            ),
            FixtureTransportResponse(
                provider=self.primary, status_code=OUTAGE_STATUS, body="unavailable"
            ),
        ]
        self.secondary_script = [
            FixtureTransportResponse(
                provider=self.secondary,
                status_code=200,
                payload={"source": self.secondary, "fixture": True},
            )
        ]
        self._reset()
        result = self.request()
        # With failure_threshold=2, first 503 does not trip; request() continues to secondary.
        ok = result.get("status") == "OK" and result.get("provider") == self.secondary
        exhausted = retries_exhausted(5, max_retries=5)
        return {
            "scenario": "provider_outage_failover",
            "pass": ok and exhausted,
            "result": result,
            "call_log": list(self.call_log),
            "retries_exhausted_at_max": exhausted,
            "fixture_only": True,
            "live_network": False,
        }


def build_default_failover_proofs() -> dict[str, Any]:
    sim = ProviderFailoverSimulator()
    rate = sim.run_rate_limit_failover_scenario()
    outage = sim.run_outage_failover_scenario()
    return {
        "rate_limit_failover": rate,
        "outage_failover": outage,
        "pass": bool(rate.get("pass") and outage.get("pass")),
        "fixture_only": True,
        "live_network": False,
    }
