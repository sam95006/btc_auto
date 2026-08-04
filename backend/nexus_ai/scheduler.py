"""Independent per-provider schedulers with bucket + breaker + retry policy."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from backend.nexus_ai.idempotency import SuccessfulCallDeduper, make_idempotency_key
from backend.nexus_ai.profiles import (
    DEFAULT_BUCKET_PARAMS,
    MAX_PROVIDER_RETRIES,
    PROVIDER_PROFILES,
)
from backend.nexus_provider.circuit_breaker import ProviderCircuitBreaker
from backend.nexus_provider.retry_policy import (
    backoff_with_jitter,
    next_resume_iso,
    parse_rate_limit_reset,
    parse_retry_after,
)
from backend.nexus_provider.token_bucket import TokenBucket
from backend.nexus_provider.transport_status import classify_transport_status


@dataclass
class ProviderQueueState:
    profile_id: str
    pending: list[str] = field(default_factory=list)
    in_flight: list[str] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    attempt_count: int = 0
    success_count: int = 0
    http_429_count: int = 0
    timeout_count: int = 0
    invalid_schema_count: int = 0
    other_failure_count: int = 0
    next_resume_not_before: str | None = None
    retry_after: float | None = None
    last_exit_reason: str | None = None
    model_id: str = ""
    retries_by_case: dict[str, int] = field(default_factory=dict)


@dataclass
class ScheduleDecision:
    allowed: bool
    reason: str
    transport_status: str | None = None
    delay_s: float = 0.0
    next_resume_not_before: str | None = None


class ProviderScheduler:
    """Four independent queues; failure in one never blocks others."""

    def __init__(
        self,
        *,
        bucket_params: dict[str, tuple[float, float]] | None = None,
        breaker: ProviderCircuitBreaker | None = None,
        deduper: SuccessfulCallDeduper | None = None,
        max_retries: int = MAX_PROVIDER_RETRIES,
        default_retry_after_s: float = 900.0,
        sleep_fn: Callable[[float], None] | None = None,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        params = bucket_params or DEFAULT_BUCKET_PARAMS
        self.buckets: dict[str, TokenBucket] = {
            p: TokenBucket(capacity=params[p][0], refill_rate=params[p][1])
            for p in PROVIDER_PROFILES
        }
        self.breaker = breaker or ProviderCircuitBreaker()
        self.deduper = deduper or SuccessfulCallDeduper()
        self.max_retries = max_retries
        self.default_retry_after_s = default_retry_after_s
        self.sleep_fn = sleep_fn or time.sleep
        self.time_fn = time_fn or time.time
        self.queues: dict[str, ProviderQueueState] = {
            p: ProviderQueueState(profile_id=p) for p in PROVIDER_PROFILES
        }

    def enqueue(self, profile_id: str, case_ids: list[str]) -> None:
        q = self.queues[profile_id]
        for cid in case_ids:
            if cid in q.completed or cid in q.pending or cid in q.in_flight:
                continue
            if self.deduper.already_completed(profile_id, cid):
                continue
            q.pending.append(cid)

    def _resume_blocked(self, q: ProviderQueueState, *, now_epoch: float) -> ScheduleDecision | None:
        nrb = q.next_resume_not_before
        if not nrb:
            return None
        try:
            dt = datetime.strptime(nrb, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if dt.timestamp() > now_epoch:
                delay = dt.timestamp() - now_epoch
                return ScheduleDecision(
                    allowed=False,
                    reason="NEXT_RESUME_NOT_BEFORE",
                    transport_status="RATE_LIMITED",
                    delay_s=delay,
                    next_resume_not_before=nrb,
                )
        except ValueError:
            return None
        return None

    def can_dispatch(self, profile_id: str, case_id: str) -> ScheduleDecision:
        q = self.queues[profile_id]
        now_epoch = self.time_fn()
        now_mono = time.monotonic()

        if self.deduper.already_completed(profile_id, case_id):
            return ScheduleDecision(
                allowed=False,
                reason="SUCCESSFUL_CASE_DEDUP",
                transport_status="DEDUP_SKIPPED",
            )

        blocked = self._resume_blocked(q, now_epoch=now_epoch)
        if blocked is not None:
            return blocked

        if self.breaker.is_open(profile_id, now=now_mono):
            st = self.breaker.status(profile_id, now=now_mono)
            return ScheduleDecision(
                allowed=False,
                reason="CIRCUIT_BREAKER_OPEN",
                transport_status="CIRCUIT_OPEN",
                delay_s=float(st.get("open_remaining_s") or 0.0),
            )

        retries = int(q.retries_by_case.get(case_id) or 0)
        if retries >= self.max_retries:
            return ScheduleDecision(
                allowed=False,
                reason="MAX_RETRY_EXCEEDED",
                transport_status="OTHER_FAILURE",
            )

        wait = self.buckets[profile_id].time_until_available(1.0)
        if wait > 0:
            return ScheduleDecision(
                allowed=False,
                reason="TOKEN_BUCKET_THROTTLED",
                transport_status="BUCKET_THROTTLED",
                delay_s=wait,
            )

        return ScheduleDecision(allowed=True, reason="OK")

    def begin_attempt(
        self,
        profile_id: str,
        case_id: str,
        *,
        prompt_hash: str,
        schema_version: str,
    ) -> tuple[ScheduleDecision, str | None]:
        decision = self.can_dispatch(profile_id, case_id)
        if not decision.allowed:
            return decision, None
        if not self.buckets[profile_id].try_acquire(1.0):
            wait = self.buckets[profile_id].time_until_available(1.0)
            return (
                ScheduleDecision(
                    allowed=False,
                    reason="TOKEN_BUCKET_THROTTLED",
                    transport_status="BUCKET_THROTTLED",
                    delay_s=wait,
                ),
                None,
            )
        idem = make_idempotency_key(
            profile_id=profile_id,
            case_id=case_id,
            prompt_hash=prompt_hash,
            schema_version=schema_version,
        )
        if not self.deduper.register_idempotency_key(idem):
            return (
                ScheduleDecision(
                    allowed=False,
                    reason="IDEMPOTENT_DUPLICATE_REQUEST",
                    transport_status="IDEMPOTENT_REPLAY",
                ),
                idem,
            )
        q = self.queues[profile_id]
        if case_id in q.pending:
            q.pending = [x for x in q.pending if x != case_id]
        if case_id not in q.in_flight:
            q.in_flight.append(case_id)
        q.attempt_count += 1
        return decision, idem

    def record_outcome(
        self,
        profile_id: str,
        case_id: str,
        *,
        http_status: int | None = None,
        result_status: str | None = None,
        headers: dict[str, Any] | None = None,
        invalid_json: bool = False,
        invalid_schema: bool = False,
        timeout: bool = False,
        response_hash: str | None = None,
        callback_fingerprint: str | None = None,
    ) -> str:
        q = self.queues[profile_id]
        q.in_flight = [x for x in q.in_flight if x != case_id]

        if callback_fingerprint is not None:
            if not self.deduper.register_callback_fingerprint(callback_fingerprint):
                return "IDEMPOTENT_REPLAY"

        status = classify_transport_status(
            http_status=http_status,
            result_status=result_status,
            invalid_json=invalid_json,
            invalid_schema=invalid_schema,
            timeout=timeout,
        )

        if status == "SUCCESS":
            q.success_count += 1
            q.last_exit_reason = "SUCCESS"
            if case_id not in q.completed:
                q.completed.append(case_id)
            self.deduper.mark_completed(
                profile_id, case_id, response_hash=response_hash or ""
            )
            self.breaker.record_success(profile_id)
            q.retry_after = None
            q.next_resume_not_before = None
            return status

        q.retries_by_case[case_id] = int(q.retries_by_case.get(case_id) or 0) + 1
        if case_id not in q.pending and case_id not in q.completed:
            q.pending.append(case_id)

        if status == "RATE_LIMITED":
            q.http_429_count += 1
            q.last_exit_reason = "PROVIDER_RATE_LIMITED"
            delay = parse_retry_after(
                headers,
                now=self.time_fn(),
                default_s=None,
            )
            if delay is None:
                reset = parse_rate_limit_reset(headers, now=self.time_fn())
                delay = reset if reset is not None else self.default_retry_after_s
            # Bound with jittered backoff floor
            attempt = int(q.retries_by_case.get(case_id) or 1) - 1
            delay = max(float(delay), backoff_with_jitter(attempt, base_s=2.0, max_s=900.0))
            q.retry_after = float(delay)
            q.next_resume_not_before = next_resume_iso(delay)
            self.breaker.record_failure(profile_id, cooldown_seconds=delay)
            return status

        if status == "TIMEOUT":
            q.timeout_count += 1
            q.last_exit_reason = "PROVIDER_TIMEOUT"
            attempt = int(q.retries_by_case.get(case_id) or 1) - 1
            delay = backoff_with_jitter(attempt, base_s=1.5, max_s=120.0)
            q.retry_after = float(delay)
            q.next_resume_not_before = next_resume_iso(delay)
            self.breaker.record_failure(profile_id, cooldown_seconds=min(delay, 60.0))
            return status

        if status in {"INVALID_JSON", "INVALID_SCHEMA"}:
            q.invalid_schema_count += 1
            q.last_exit_reason = "PROVIDER_SCHEMA_FAILURE"
            self.breaker.record_failure(profile_id)
            return status

        q.other_failure_count += 1
        q.last_exit_reason = status
        self.breaker.record_failure(profile_id)
        return status

    def snapshot(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for pid, q in self.queues.items():
            out[pid] = {
                "profile_id": pid,
                "model_id": q.model_id,
                "pending_count": len(q.pending),
                "in_flight_count": len(q.in_flight),
                "completed_count": len(q.completed),
                "attempt_count": q.attempt_count,
                "success_count": q.success_count,
                "HTTP_429_count": q.http_429_count,
                "timeout_count": q.timeout_count,
                "invalid_schema_count": q.invalid_schema_count,
                "other_failure_count": q.other_failure_count,
                "retry_after": q.retry_after,
                "next_resume_not_before": q.next_resume_not_before,
                "last_exit_reason": q.last_exit_reason,
                "bucket": self.buckets[pid].snapshot(),
                "circuit_breaker": self.breaker.status(pid),
            }
        return out

    def export_transport_for_checkpoint(self) -> dict[str, Any]:
        """Shape compatible with quota_aware_v23 transport slots."""
        snap = self.snapshot()
        transport: dict[str, Any] = {}
        for pid, s in snap.items():
            transport[pid] = {
                "profile_id": pid,
                "model_id": s.get("model_id") or "",
                "attempt_count": s["attempt_count"],
                "success_count": s["success_count"],
                "HTTP_429_count": s["HTTP_429_count"],
                "timeout_count": s["timeout_count"],
                "invalid_schema_count": s["invalid_schema_count"],
                "other_failure_count": s["other_failure_count"],
                "last_attempt_at": None,
                "retry_after": s.get("retry_after"),
                "next_resume_not_before": s.get("next_resume_not_before"),
                "last_exit_reason": s.get("last_exit_reason"),
            }
        return transport
