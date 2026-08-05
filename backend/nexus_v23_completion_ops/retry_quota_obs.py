"""Retry-After and quota-reset visibility — no secret logging."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from backend.nexus_provider.retry_policy import (
    next_resume_iso,
    parse_quota_reset_at,
    parse_rate_limit_reset,
    parse_retry_after,
)
from backend.nexus_v23_completion_ops.constants import SCHEMA_RETRY_QUOTA
from backend.nexus_v23_completion_ops.sanitize import safe_log_fields


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_dt(now: float | datetime | None) -> datetime | None:
    if now is None:
        return None
    if isinstance(now, datetime):
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return datetime.fromtimestamp(float(now), tz=timezone.utc)


def observe_retry_and_quota(
    *,
    profile_id: str,
    headers: Mapping[str, Any] | None = None,
    http_status: int | None = None,
    now: float | datetime | None = None,
) -> dict[str, Any]:
    wait_s = parse_retry_after(headers, now=now, default_s=None)
    quota_s = parse_rate_limit_reset(headers, now=now)
    quota_at = parse_quota_reset_at(headers, now=now)
    next_not_before = next_resume_iso(wait_s, now_dt=_as_dt(now)) if wait_s is not None else None
    safe_headers: dict[str, str] = {}
    if headers:
        for k, v in headers.items():
            lk = str(k).lower()
            if lk in {"authorization", "x-api-key", "api_key", "api_secret"}:
                continue
            if lk in {
                "retry-after",
                "x-retry-after",
                "x-ratelimit-reset",
                "x-ratelimit-remaining",
                "x-ratelimit-limit",
            }:
                safe_headers[str(k)] = str(v)
    event = {
        "schema": SCHEMA_RETRY_QUOTA,
        "created_at": _utc(),
        "profile_id": profile_id,
        "http_status": http_status,
        "retry_after_s": wait_s,
        "quota_reset_s": quota_s,
        "quota_reset_at": (
            quota_at.strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(quota_at, datetime) else None
        ),
        "quota_reset_visible": quota_s is not None,
        "next_resume_not_before": next_not_before,
        "rate_limited": http_status == 429 or (wait_s is not None and wait_s > 0),
        "headers_observed": safe_headers,
        "secret_logging": False,
    }
    return safe_log_fields(event)


def observe_lane_retry_quota_map(
    lane_headers: Mapping[str, Mapping[str, Any] | None],
    *,
    now: float | datetime | None = None,
) -> dict[str, Any]:
    observations = {
        pid: observe_retry_and_quota(profile_id=pid, headers=hdrs, http_status=429, now=now)
        for pid, hdrs in lane_headers.items()
    }
    waits = [o.get("retry_after_s") for o in observations.values() if o.get("retry_after_s") is not None]
    quotas = [o.get("quota_reset_s") for o in observations.values() if o.get("quota_reset_s") is not None]
    return {
        "schema": f"{SCHEMA_RETRY_QUOTA}_map",
        "created_at": _utc(),
        "lanes": observations,
        "max_retry_after_s": max(waits) if waits else None,
        "max_quota_reset_s": max(quotas) if quotas else None,
        "any_rate_limited": any(bool(o.get("rate_limited")) for o in observations.values()),
        "any_quota_reset_visible": any(bool(o.get("quota_reset_visible")) for o in observations.values()),
        "secret_logging": False,
    }
