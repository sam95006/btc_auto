"""Retry-After observability — parse and surface waits without secret logging."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from backend.nexus_provider.retry_policy import next_resume_iso, parse_retry_after
from backend.nexus_provider_ops.constants import SCHEMA_RETRY_AFTER
from backend.nexus_provider_ops.sanitize import safe_log_fields


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_dt(now: float | datetime | None) -> datetime | None:
    if now is None:
        return None
    if isinstance(now, datetime):
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return datetime.fromtimestamp(float(now), tz=timezone.utc)


def observe_retry_after(
    *,
    profile_id: str,
    headers: Mapping[str, Any] | None = None,
    http_status: int | None = None,
    body: str | None = None,
    now: float | datetime | None = None,
) -> dict[str, Any]:
    """Observe Retry-After for a provider lane; never log Authorization / API keys."""
    wait_s = parse_retry_after(headers, body=body, now=now, default_s=None)
    next_not_before = (
        next_resume_iso(wait_s, now_dt=_as_dt(now)) if wait_s is not None else None
    )
    # Only retain safe header names for observability
    safe_headers: dict[str, str] = {}
    if headers:
        for k, v in headers.items():
            lk = str(k).lower()
            if lk in {"authorization", "x-api-key", "api_key", "api_secret"}:
                continue
            if lk in {"retry-after", "x-retry-after", "x-ratelimit-reset", "x-ratelimit-remaining"}:
                safe_headers[str(k)] = str(v)

    event = {
        "schema": SCHEMA_RETRY_AFTER,
        "created_at": _utc(),
        "profile_id": profile_id,
        "http_status": http_status,
        "retry_after_s": wait_s,
        "next_resume_not_before": next_not_before,
        "rate_limited": http_status == 429 or (wait_s is not None and wait_s > 0),
        "headers_observed": safe_headers,
        "body_parsed": body is not None and wait_s is not None and not safe_headers,
        "secret_logging": False,
    }
    return safe_log_fields(event)


def observe_lane_retry_map(
    lane_headers: Mapping[str, Mapping[str, Any] | None],
    *,
    now: float | datetime | None = None,
) -> dict[str, Any]:
    observations = {
        pid: observe_retry_after(profile_id=pid, headers=hdrs, http_status=429, now=now)
        for pid, hdrs in lane_headers.items()
    }
    waits = [o.get("retry_after_s") for o in observations.values() if o.get("retry_after_s") is not None]
    return {
        "schema": f"{SCHEMA_RETRY_AFTER}_map",
        "created_at": _utc(),
        "lanes": observations,
        "max_retry_after_s": max(waits) if waits else None,
        "any_rate_limited": any(bool(o.get("rate_limited")) for o in observations.values()),
        "secret_logging": False,
    }
