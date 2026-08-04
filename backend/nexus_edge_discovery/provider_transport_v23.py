"""Deterministic V2.3 provider transport: token-bucket, Retry-After, backoff, circuit, replay.

Transport failures (429 / timeout / circuit) are never classified as AI quality failures.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Mapping

DEFAULT_RETRY_AFTER_S = 900
DEFAULT_BUCKET_CAPACITY = 5.0
DEFAULT_BUCKET_REFILL_PER_S = 0.2  # ~12 req/min
CIRCUIT_FAILURE_THRESHOLD = 3
CIRCUIT_COOLDOWN_S = 60.0
MAX_BACKOFF_S = 120.0
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
    now: datetime | None = None,
) -> float:
    """Parse Retry-After / x-ratelimit-reset into seconds to wait (>=0)."""
    now = now or _utc_now()
    hdrs: dict[str, str] = {}
    if headers:
        for k, v in headers.items():
            if k is None or v is None:
                continue
            hdrs[str(k).lower()] = str(v).strip()

    for key in ("retry-after", "x-retry-after"):
        raw = hdrs.get(key)
        if not raw:
            continue
        try:
            return max(0.0, float(raw))
        except ValueError:
            try:
                dt = parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return max(0.0, (dt - now).total_seconds())
            except Exception:
                continue

    for key in (
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
        "x-ratelimit-reset",
        "ratelimit-reset",
    ):
        raw = hdrs.get(key)
        if not raw:
            continue
        try:
            val = float(raw)
        except ValueError:
            continue
        # Absolute unix epoch vs relative seconds heuristic.
        if val > 1_000_000_000:
            return max(0.0, val - now.timestamp())
        return max(0.0, val)

    if body:
        low = body.lower()
        # Common Groq/SambaNova JSON: {"error":{"message":"...try again in 12.5s..."}}
        for marker in ("try again in ", "retry after ", "please retry after "):
            idx = low.find(marker)
            if idx < 0:
                continue
            frag = low[idx + len(marker) : idx + len(marker) + 32]
            num = ""
            for ch in frag:
                if ch.isdigit() or ch == ".":
                    num += ch
                elif num:
                    break
            if num:
                try:
                    return max(0.0, float(num))
                except ValueError:
                    pass

    return float(default_s)


def parse_quota_reset_at(
    headers: Mapping[str, Any] | None,
    *,
    now: datetime | None = None,
) -> datetime | None:
    """Return absolute UTC datetime when provider quota resets, if advertised."""
    now = now or _utc_now()
    if not headers:
        return None
    hdrs = {str(k).lower(): str(v).strip() for k, v in headers.items() if k is not None and v is not None}
    for key in ("x-ratelimit-reset", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
        raw = hdrs.get(key)
        if not raw:
            continue
        try:
            val = float(raw)
        except ValueError:
            continue
        if val > 1_000_000_000:
            return datetime.fromtimestamp(val, tz=timezone.utc)
        return now + timedelta(seconds=val)
    raw = hdrs.get("retry-after")
    if raw:
        try:
            return now + timedelta(seconds=float(raw))
        except ValueError:
            try:
                dt = parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                return None
    return None


def exponential_backoff_with_jitter(
    attempt: int,
    *,
    base_s: float = 1.0,
    cap_s: float = MAX_BACKOFF_S,
    jitter_ratio: float = 0.25,
    rng: random.Random | None = None,
) -> float:
    """Full-jitter exponential backoff. attempt is 0-indexed."""
    exp = min(cap_s, base_s * (2 ** max(0, attempt)))
    span = exp * max(0.0, min(1.0, jitter_ratio))
    r = rng or random
    return max(0.0, exp - span + r.random() * (2 * span))


@dataclass
class TokenBucket:
    """Provider-specific token bucket (capacity tokens, refill_per_s)."""

    capacity: float = DEFAULT_BUCKET_CAPACITY
    refill_per_s: float = DEFAULT_BUCKET_REFILL_PER_S
    tokens: float = DEFAULT_BUCKET_CAPACITY
    updated_at: float = field(default_factory=time.monotonic)
    profile_id: str = ""

    def _refill(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        elapsed = max(0.0, now - self.updated_at)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_s)
        self.updated_at = now

    def try_acquire(self, cost: float = 1.0, *, now: float | None = None) -> bool:
        self._refill(now)
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def time_until_available(self, cost: float = 1.0, *, now: float | None = None) -> float:
        self._refill(now)
        if self.tokens >= cost:
            return 0.0
        need = cost - self.tokens
        if self.refill_per_s <= 0:
            return math.inf
        return need / self.refill_per_s

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "capacity": self.capacity,
            "refill_per_s": self.refill_per_s,
            "tokens": round(self.tokens, 4),
        }


@dataclass
class CircuitBreaker:
    """Open after consecutive transport failures; half-open after cooldown."""

    failure_threshold: int = CIRCUIT_FAILURE_THRESHOLD
    cooldown_s: float = CIRCUIT_COOLDOWN_S
    consecutive_failures: int = 0
    opened_at: float | None = None
    state: str = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
    last_failure_status: str | None = None
    profile_id: str = ""

    def allow(self, *, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if self.opened_at is None:
                return False
            if (now - self.opened_at) >= self.cooldown_s:
                self.state = "HALF_OPEN"
                return True
            return False
        # HALF_OPEN — allow one probe
        return True

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.opened_at = None
        self.state = "CLOSED"
        self.last_failure_status = None

    def record_failure(self, status: str, *, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self.last_failure_status = status
        # 429 opens circuit immediately for capacity isolation
        if status == "RATE_LIMITED":
            self.consecutive_failures = self.failure_threshold
            self.opened_at = now
            self.state = "OPEN"
            return
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_threshold or self.state == "HALF_OPEN":
            self.opened_at = now
            self.state = "OPEN"

    def to_dict(self) -> dict[str, Any]:
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
        target = now + timedelta(seconds=max(0.0, wait_s))
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
        wait = parse_retry_after(headers, body=body, now=now)
        reset_at = parse_quota_reset_at(headers, now=now)
        if reset_at is not None:
            self.quota_reset_at = reset_at
            wait = max(wait, (reset_at - now).total_seconds())
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
            wait = exponential_backoff_with_jitter(attempt, rng=self.rng)
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
    return str(status or "").upper() in TRANSPORT_ONLY_STATUSES


def is_ai_quality_failure(status: str | None) -> bool:
    """429 / timeout / circuit are never AI quality failures."""
    s = str(status or "").upper()
    if s in TRANSPORT_ONLY_STATUSES or s == "RATE_LIMITED" or "429" in s:
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
