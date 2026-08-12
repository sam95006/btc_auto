"""Fixture-only Provider preflight — Background Agent never owns real Provider calls."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from backend.nexus_ai.profiles import GROQ_REFLECTION_REASONER, SAMBANOVA_INDEPENDENT_CRITIC
from backend.nexus_provider.retry_policy import (
    next_resume_iso,
    parse_quota_reset_at,
    parse_rate_limit_reset,
    parse_retry_after,
)
from backend.nexus_v23_completion_ops.constants import PROVIDER_LANES, REAL_RESUME_OWNER, SCHEMA_PREFLIGHT
from backend.nexus_v23_completion_ops.sanitize import assert_no_secret_keys, safe_log_fields


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fixture_provider_preflight(
    profile_id: str,
    *,
    headers: Mapping[str, Any] | None = None,
    http_status: int | None = 429,
    result_status: str = "RATE_LIMITED",
    now: float | None = None,
) -> dict[str, Any]:
    """Sanitized preflight observation. Does not invoke live providers."""
    if profile_id not in PROVIDER_LANES:
        raise KeyError(f"unknown_provider_lane:{profile_id}")
    wait = parse_retry_after(headers, now=now, default_s=900.0)
    quota_s = parse_rate_limit_reset(headers, now=now)
    quota_at = parse_quota_reset_at(headers, now=now)
    ok = result_status in {"OK", "SUCCESS"} and http_status in {None, 200}
    report = {
        "schema": SCHEMA_PREFLIGHT,
        "created_at": _utc(),
        "profile_id": profile_id,
        "mode": "SANITIZED_FIXTURE",
        "provider_preflight_status": (
            "PASS" if ok else ("RATE_LIMITED" if result_status == "RATE_LIMITED" else result_status)
        ),
        "result_status": result_status,
        "http_status": http_status,
        "retry_after_s": wait,
        "quota_reset_s": quota_s,
        "quota_reset_at": (
            quota_at.strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(quota_at, datetime) else None
        ),
        "next_resume_not_before": next_resume_iso(wait) if wait is not None else None,
        "mass_batch_blocked": not ok,
        "real_provider_call_executed": False,
        "real_resume_owner": REAL_RESUME_OWNER,
        "ops_owns_real_resume": False,
        "api_key_recorded": False,
        "secret_logging": False,
        "fixture_label": "CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING",
    }
    return safe_log_fields(report)


def run_lane_preflights(
    *,
    groq_headers: Mapping[str, Any] | None = None,
    sambanova_headers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    groq_headers = groq_headers or {"Retry-After": "900", "x-ratelimit-reset": "900"}
    sambanova_headers = sambanova_headers or {"Retry-After": "900", "x-ratelimit-reset": "1200"}
    lanes = {
        GROQ_REFLECTION_REASONER: fixture_provider_preflight(
            GROQ_REFLECTION_REASONER, headers=groq_headers
        ),
        SAMBANOVA_INDEPENDENT_CRITIC: fixture_provider_preflight(
            SAMBANOVA_INDEPENDENT_CRITIC, headers=sambanova_headers
        ),
    }
    out = {
        "schema": f"{SCHEMA_PREFLIGHT}_map",
        "created_at": _utc(),
        "lanes": lanes,
        "any_mass_batch_blocked": any(v.get("mass_batch_blocked") for v in lanes.values()),
        "real_provider_call_executed": False,
        "background_agent_mode": "sanitized_fixtures_only",
        "V2_3_complete": False,
    }
    assert_no_secret_keys(out)
    return out
