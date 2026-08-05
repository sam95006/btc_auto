"""Deterministic V2.3 provider transport: token-bucket, Retry-After, backoff, circuit, replay.

Retry / backoff / quota / transport-classification AUTHORITY lives in
``backend.nexus_provider``. This module adapts provider-specific VALUES and
orchestrates queues; it must not redefine retry algorithms.

Transport failures (429 / timeout / circuit) are never classified as AI quality failures.
"""
from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from backend.nexus_provider.circuit_breaker import ProviderCircuitBreaker
from backend.nexus_provider.retry_policy import (
    DEFAULT_RETRY_AFTER_S as _CANONICAL_DEFAULT_RETRY_AFTER_S,
    MAX_BACKOFF_S as _CANONICAL_MAX_BACKOFF_S,
    compute_resume_wait_s,
    exponential_backoff_with_jitter,
    next_resume_iso,
    parse_quota_reset_at,
    parse_retry_after as _canonical_parse_retry_after,
)
from backend.nexus_provider.token_bucket import TokenBucket
from backend.nexus_provider.transport_status import (
    is_quality_neutral_transport,
)

# Re-export canonical constants (provider VALUES may override at call sites).
DEFAULT_RETRY_AFTER_S = float(_CANONICAL_DEFAULT_RETRY_AFTER_S)
DEFAULT_BUCKET_CAPACITY = 5.0
DEFAULT_BUCKET_REFILL_PER_S = 0.2  # ~12 req/min
CIRCUIT_FAILURE_THRESHOLD = 3
CIRCUIT_COOLDOWN_S = 60.0
MAX_BACKOFF_S = min(120.0, float(_CANONICAL_MAX_BACKOFF_S))
CHECKPOINT_SCHEMA_V3 = "blind_reflection_v23_checkpoint_v3"
PROFILES = (
    "GROQ_REFLECTION_REASONER",
    "SAMBANOVA_INDEPENDENT_CRITIC",
    "CEREBRAS_RESEARCH_NORMALIZER",
    "GROQ_MAIN_REASONER",
)

# Result statuses that are transport/capacity — never AI quality failures.
TRANSPORT_ONLY_STATUSES = frozenset(
    {
        "RATE_LIMITED",
        "TIMEOUT",
        "PROVIDER_UNAVAILABLE",
        "MODEL_UNAVAILABLE",
        "CIRCUIT_OPEN",
        "TOKEN_BUCKET_WAIT",
        "QUOTA_RESET_WAIT",
    }
)

QUALITY_EVALUABLE_STATUSES = frozenset({"OK", "SUCCESS", "INVALID_SCHEMA"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_str(dt: datetime | None = None) -> str:
    return (dt or _utc_now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_retry_after(
    headers: Mapping[str, Any] | None,
    *,
    body: str | None = None,
    default_s: float = DEFAULT_RETRY_AFTER_S,
    now: datetime | float | None = None,
) -> float:
    """Adapter: always returns a float using canonical retry authority."""
    wait = _canonical_parse_retry_after(
        headers, body=body, now=now, default_s=default_s
    )
    return float(wait if wait is not None else default_s)


@dataclass
class CircuitBreaker:
    """Per-profile facade over canonical ``ProviderCircuitBreaker``.

    Preserves the single-instance V2.3 API while algorithm authority remains
    in ``backend.nexus_provider.circuit_breaker``.
    """

    failure_threshold: int = CIRCUIT_FAILURE_THRESHOLD
    cooldown_s: float = CIRCUIT_COOLDOWN_S
    consecutive_failures: int = 0
    opened_at: float | None = None
    state: str = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
    last_failure_status: str | None = None
    profile_id: str = ""
    _inner: ProviderCircuitBreaker = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._inner = ProviderCircuitBreaker(
            failure_threshold=self.failure_threshold,
            cooldown_seconds=self.cooldown_s,
        )

    def _key(self) -> str:
        return self.profile_id or "_default"

    def _sync_from_inner(self, *, now: float | None = None) -> None:
        st = self._inner.status(self._key(), now=now)
        self.state = str(st["state"])
        self.consecutive_failures = int(st["failures"])
        if self.state == "OPEN":
            rem = float(st.get("open_remaining_s") or 0.0)
            mono = time.monotonic() if now is None else now
            self.opened_at = mono - (self.cooldown_s - rem) if rem > 0 else mono
        elif self.state == "CLOSED":
            self.opened_at = None

    def allow(self, *, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        open_ = self._inner.is_open(self._key(), now=now)
        self._sync_from_inner(now=now)
        if open_:
            return False
        # half-open or closed → allow probe / traffic
        return True

    def record_success(self) -> None:
        self._inner.record_success(self._key())
        self.last_failure_status = None
        self._sync_from_inner()

    def record_failure(self, status: str, *, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self.last_failure_status = status
        if status == "RATE_LIMITED":
            self._inner.record_rate_limit(
                self._key(), cooldown_seconds=self.cooldown_s, now=now
            )
        else:
            self._inner.record_failure(
                self._key(), cooldown_seconds=self.cooldown_s, now=now
            )
        self._sync_from_inner(now=now)

    def to_dict(self) -> dict[str, Any]:
        self._sync_from_inner()
        return {
            "profile_id": self.profile_id,
            "state": self.state,
            "consecutive_failures": self.consecutive_failures,
            "last_failure_status": self.last_failure_status,
            "failure_threshold": self.failure_threshold,
            "cooldown_s": self.cooldown_s,
        }


@dataclass
class ProviderTransportController:
    """Independent per-provider scheduling: bucket + circuit + resume clock."""

    profile_id: str
    bucket: TokenBucket = field(default_factory=TokenBucket)
    circuit: CircuitBreaker = field(default_factory=CircuitBreaker)
    next_resume_not_before: datetime | None = None
    quota_reset_at: datetime | None = None
    last_retry_after_s: float | None = None
    rng: random.Random = field(default_factory=random.Random)

    def __post_init__(self) -> None:
        self.bucket.profile_id = self.profile_id
        self.circuit.profile_id = self.profile_id

    def schedule_resume(
        self,
        wait_s: float,
        *,
        now: datetime | None = None,
        reason: str = "RETRY_AFTER",
    ) -> datetime:
        now = now or _utc_now()
        # next-resume timestamp authority: canonical ISO formatter
        resume_iso = next_resume_iso(wait_s, now_dt=now)
        target = datetime.strptime(resume_iso, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        if self.next_resume_not_before is None or target > self.next_resume_not_before:
            self.next_resume_not_before = target
        self.last_retry_after_s = wait_s
        if reason == "QUOTA_RESET":
            self.quota_reset_at = target
        return target

    def apply_rate_limit(
        self,
        headers: Mapping[str, Any] | None = None,
        *,
        body: str | None = None,
        now: datetime | None = None,
    ) -> float:
        now = now or _utc_now()
        wait = compute_resume_wait_s(
            headers, body=body, now=now, default_s=DEFAULT_RETRY_AFTER_S
        )
        reset_at = parse_quota_reset_at(headers, now=now)
        if reset_at is not None:
            self.quota_reset_at = reset_at
            self.schedule_resume(wait, now=now, reason="QUOTA_RESET")
        else:
            self.schedule_resume(wait, now=now, reason="RETRY_AFTER")
        self.circuit.record_failure("RATE_LIMITED")
        return wait

    def can_invoke(self, *, now: datetime | None = None) -> tuple[bool, str]:
        now = now or _utc_now()
        if self.next_resume_not_before and now < self.next_resume_not_before:
            return False, "QUOTA_RESET_WAIT" if (
                self.quota_reset_at and now < self.quota_reset_at
            ) else "TOKEN_BUCKET_WAIT"
        if not self.circuit.allow():
            return False, "CIRCUIT_OPEN"
        if not self.bucket.try_acquire():
            return False, "TOKEN_BUCKET_WAIT"
        return True, "OK"

    def on_result(self, status: str, *, headers: Mapping[str, Any] | None = None, body: str | None = None) -> None:
        if status in {"OK", "SUCCESS"}:
            self.circuit.record_success()
            self.next_resume_not_before = None
            self.last_retry_after_s = None
            return
        if status == "RATE_LIMITED":
            self.apply_rate_limit(headers, body=body)
            return
        if status in TRANSPORT_ONLY_STATUSES | {"INVALID_SCHEMA", "UNKNOWN"}:
            self.circuit.record_failure(status)
            attempt = max(0, self.circuit.consecutive_failures - 1)
            wait = exponential_backoff_with_jitter(
                attempt, max_s=MAX_BACKOFF_S, rng=self.rng
            )
            self.schedule_resume(wait, reason=status)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "bucket": self.bucket.to_dict(),
            "circuit": self.circuit.to_dict(),
            "next_resume_not_before": _utc_str(self.next_resume_not_before)
            if self.next_resume_not_before
            else None,
            "quota_reset_at": _utc_str(self.quota_reset_at) if self.quota_reset_at else None,
            "last_retry_after_s": self.last_retry_after_s,
        }


def is_transport_failure(status: str | None) -> bool:
    s = str(status or "").upper()
    return s in TRANSPORT_ONLY_STATUSES or is_quality_neutral_transport(s)


def is_ai_quality_failure(status: str | None) -> bool:
    """429 / timeout / circuit are never AI quality failures (canonical taxonomy)."""
    s = str(status or "").upper()
    if s in TRANSPORT_ONLY_STATUSES or is_quality_neutral_transport(s) or "429" in s:
        return False
    return s == "INVALID_SCHEMA"


def dedupe_pending_against_success(
    *,
    case_ids: list[str],
    completed_case_ids: list[str],
    pending_case_ids: list[str] | None = None,
) -> list[str]:
    """Resume scheduling: never re-queue successful cases."""
    done = set(completed_case_ids)
    source = pending_case_ids if pending_case_ids is not None else case_ids
    out: list[str] = []
    seen: set[str] = set()
    for cid in source:
        if cid in done or cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
    # Also include case_ids not completed and not already pending (resume completeness)
    if pending_case_ids is not None:
        for cid in case_ids:
            if cid in done or cid in seen:
                continue
            seen.add(cid)
            out.append(cid)
    return out


@dataclass
class ReplayFixtureStore:
    """Replay provider responses from sanitized fixtures (no secrets)."""

    fixtures: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_dir(cls, path: Path) -> "ReplayFixtureStore":
        store = cls()
        if not path.is_dir():
            return store
        for fp in sorted(path.glob("*.json")):
            try:
                data = json.loads(fp.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            key = str(data.get("fixture_key") or fp.stem)
            # Strip any accidental secret-bearing fields
            for banned in ("api_key", "Authorization", "raw_prompt", "raw_response"):
                data.pop(banned, None)
            store.fixtures[key] = data
        return store

    def get(
        self,
        *,
        profile_id: str,
        trade_id: str | None = None,
        prompt_schema_version: str | None = None,
    ) -> dict[str, Any] | None:
        keys = [
            f"{profile_id}:{trade_id}:{prompt_schema_version}",
            f"{profile_id}:{trade_id}",
            f"{profile_id}:{prompt_schema_version}",
            profile_id,
        ]
        for k in keys:
            if k in self.fixtures:
                return self.fixtures[k]
        return None

    def invoke(
        self,
        *,
        profile_id: str,
        trade_id: str | None = None,
        prompt_schema_version: str | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        fx = self.get(
            profile_id=profile_id,
            trade_id=trade_id,
            prompt_schema_version=prompt_schema_version,
        )
        if fx is None:
            return None, {
                "result_status": "PROVIDER_UNAVAILABLE",
                "smoke_map": "REPLAY_FIXTURE_MISSING",
                "replay": True,
            }
        status = str(fx.get("result_status") or "SUCCESS")
        body = fx.get("body")
        if isinstance(body, dict):
            parsed = body
        else:
            parsed = None
        rec = {
            "result_status": status if status != "OK" else "SUCCESS",
            "smoke_map": fx.get("smoke_map") or status,
            "replay": True,
            "fixture_key": fx.get("fixture_key"),
            "http_status": fx.get("http_status"),
            "headers": fx.get("headers") or {},
            "latency_ms": fx.get("latency_ms") or 0,
        }
        if status in {"RATE_LIMITED", "TIMEOUT", "INVALID_SCHEMA", "CIRCUIT_OPEN"}:
            return None, rec
        return parsed, rec


def detect_checkpoint_corruption(state: Any) -> dict[str, Any]:
    """Detect corrupt / unreadable checkpoint structures without mutating."""
    issues: list[str] = []
    if not isinstance(state, dict):
        return {
            "corrupt": True,
            "issues": ["not_a_dict"],
            "recoverable": False,
            "recommended_action": "REBUILD_FROM_MANIFEST",
        }
    schema_v = state.get("schema_version")
    try:
        schema_i = int(schema_v) if schema_v is not None else 0
    except (TypeError, ValueError):
        schema_i = -1
        issues.append("schema_version_unparseable")

    case_ids = state.get("case_ids")
    if not isinstance(case_ids, list) or len(case_ids) != 80:
        issues.append("case_ids_not_80")
    completed = state.get("completed_case_ids")
    if completed is not None and not isinstance(completed, list):
        issues.append("completed_case_ids_not_list")
    pending = state.get("pending_case_ids")
    if pending is not None and not isinstance(pending, list):
        issues.append("pending_case_ids_not_list")
    case_results = state.get("case_results")
    if case_results is not None and not isinstance(case_results, dict):
        issues.append("case_results_not_dict")

    if isinstance(completed, list) and isinstance(case_results, dict):
        for cid in completed:
            if cid not in case_results:
                issues.append(f"completed_missing_result:{cid}")
                break

    # Overlap completed ∩ pending is corruption
    if isinstance(completed, list) and isinstance(pending, list):
        overlap = set(completed) & set(pending)
        if overlap:
            issues.append("completed_pending_overlap")

    checksum = state.get("calibration_manifest_checksum")
    if not checksum:
        issues.append("missing_manifest_checksum")

    transport = state.get("transport")
    if schema_i >= 3 and not isinstance(transport, dict):
        issues.append("v3_missing_transport")

    # Truncated JSON marker / null bytes
    for k in ("schema", "exit_reason", "groq_stage"):
        v = state.get(k)
        if isinstance(v, str) and "\x00" in v:
            issues.append("null_byte_in_field")

    fatal = any(
        i in issues
        for i in (
            "not_a_dict",
            "case_ids_not_80",
            "completed_case_ids_not_list",
            "case_results_not_dict",
            "schema_version_unparseable",
        )
    )
    recoverable = (not fatal) or (
        isinstance(case_ids, list)
        and len(case_ids) == 80
        and isinstance(completed, list)
        and isinstance(case_results, dict)
    )
    return {
        "corrupt": bool(issues),
        "issues": issues,
        "recoverable": recoverable and not fatal,
        "schema_version": schema_i,
        "recommended_action": (
            "MIGRATE_AND_REPAIR"
            if recoverable
            else "REBUILD_FROM_MANIFEST"
            if fatal
            else "NONE"
        ),
    }


def repair_checkpoint_overlap(state: dict[str, Any]) -> dict[str, Any]:
    """Drop completed IDs from pending; keep successes authoritative."""
    completed = list(state.get("completed_case_ids") or [])
    done = set(completed)
    state["pending_case_ids"] = [
        cid for cid in (state.get("pending_case_ids") or []) if cid not in done
    ]
    # Deduplicate completed while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for cid in completed:
        if cid in seen:
            continue
        seen.add(cid)
        uniq.append(cid)
    state["completed_case_ids"] = uniq
    return state


def validate_terminal_denominators(quality: Mapping[str, Any]) -> dict[str, Any]:
    """Ensure terminal ratios never invent 1.0 on empty / blocked denominators."""
    issues: list[str] = []
    required_ratio_keys = (
        "evidence_packet_constructible_ratio",
        "reflection_prompt_delivery_ratio_on_attempts",
        "full_calibration_completion_ratio",
        "blind_valid_schema_ratio",
        "informative_classification_ratio_overall",
        "informative_classification_ratio_on_sufficient_cases",
        "blind_agreement_ratio_on_sufficient_cases",
        "critic_resolution_ratio",
    )
    for key in required_ratio_keys:
        ratio = quality.get(key)
        if ratio is None:
            continue
        if not isinstance(ratio, dict):
            issues.append(f"{key}:not_dict")
            continue
        denom = ratio.get("denominator")
        value = ratio.get("value")
        status = ratio.get("status")
        try:
            d = float(denom) if denom is not None else 0.0
        except (TypeError, ValueError):
            issues.append(f"{key}:bad_denominator")
            continue
        if d <= 0 and value is not None:
            issues.append(f"{key}:zero_denom_nonzero_value")
        if status in {
            "NOT_APPLICABLE",
            "PROVIDER_BLOCKED",
            "GROQ_PROVIDER_BLOCKED",
            "SAMBANOVA_PROVIDER_BLOCKED",
            "PROVIDER_CAPACITY_UNKNOWN",
        } and value is not None:
            issues.append(f"{key}:blocked_status_has_value")
        if status == "INCOMPLETE_SAMPLE" and value == 1.0 and d > 0:
            # incomplete may have partial ratio, but claiming 1.0 with incomplete status is suspect
            num = float(ratio.get("numerator") or 0)
            if num < d:
                pass  # value should be num/d < 1; if value==1 with incomplete, flag
            if abs(float(value) - 1.0) < 1e-12 and num < d:
                issues.append(f"{key}:incomplete_claimed_one")

    # 429 must not flip quality_gates_passed by itself
    if quality.get("quality_gates_passed") and quality.get("V2_3_TERMINAL_STATUS") == "INCOMPLETE_PROVIDER_CAPACITY":
        issues.append("passed_while_capacity_incomplete")

    transport = quality.get("transport") or {}
    for pid, row in transport.items() if isinstance(transport, dict) else []:
        if not isinstance(row, dict):
            continue
        if int(row.get("HTTP_429_count") or 0) > 0:
            # Ensure we didn't label 429 as quality failure terminal
            if quality.get("V2_3_TERMINAL_STATUS") == "VALID_SAMPLE_QUALITY_FAILED" and not quality.get(
                "quality_gates_evaluated"
            ):
                issues.append(f"{pid}:429_misclassified_as_quality")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "checked_ratio_keys": list(required_ratio_keys),
    }


def sha_fixture_body(body: Any) -> str:
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def sleep_fn_factory(enabled: bool = True) -> Callable[[float], None]:
    if enabled:
        return time.sleep

    def _noop(_s: float) -> None:
        return None

    return _noop
