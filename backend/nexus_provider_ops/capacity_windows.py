"""Capacity windows — token-bucket informed scheduling windows (ops-only, no real resume)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.nexus_ai.profiles import (
    DEFAULT_BUCKET_PARAMS,
    GROQ_REFLECTION_REASONER,
    SAMBANOVA_INDEPENDENT_CRITIC,
)
from backend.nexus_provider.token_bucket import TokenBucket
from backend.nexus_provider_ops.constants import PROVIDER_LANES, SCHEMA_CAPACITY
from backend.nexus_provider_ops.sot import incomplete_sot_snapshot


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _window_for_profile(
    profile_id: str,
    *,
    pending_count: int,
    retry_after_s: float | None,
    now: datetime,
) -> dict[str, Any]:
    burst, refill = DEFAULT_BUCKET_PARAMS.get(profile_id, (3.0, 0.1))
    bucket = TokenBucket(capacity=burst, refill_rate=refill, profile_id=profile_id)
    tokens = float(bucket.snapshot()["tokens"])
    wait_for_one = float(bucket.time_until_available(1.0))
    # Capacity window opens after Retry-After (if any) and when bucket has a token.
    retry_wait = float(retry_after_s or 0.0)
    open_in_s = max(retry_wait, 0.0 if tokens >= 1.0 else wait_for_one)
    # Estimated drain time for remaining pending at refill rate (ops estimate only).
    drain_s = (pending_count / refill) if refill > 0 else None
    window_open_at = now + timedelta(seconds=open_in_s)
    window_close_at = (
        window_open_at + timedelta(seconds=drain_s) if drain_s is not None else None
    )
    return {
        "profile_id": profile_id,
        "burst_capacity": burst,
        "refill_per_s": refill,
        "tokens_available": tokens,
        "pending_count": int(pending_count),
        "retry_after_s": retry_after_s,
        "window_open_in_s": round(open_in_s, 3),
        "window_open_at": window_open_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "estimated_drain_s": round(drain_s, 3) if drain_s is not None else None,
        "window_close_at": (
            window_close_at.strftime("%Y-%m-%dT%H:%M:%SZ") if window_close_at else None
        ),
        "window_status": "CLOSED_WAITING" if open_in_s > 0 else "OPEN",
        "real_resume_authorized": False,
    }


def evaluate_capacity_windows(
    *,
    groq_pending: int | None = None,
    sambanova_pending: int | None = None,
    groq_retry_after_s: float | None = 900.0,
    sambanova_retry_after_s: float | None = 900.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build capacity windows around incomplete SoT pending counts."""
    sot = incomplete_sot_snapshot()
    now = now or datetime.now(timezone.utc)
    g_pending = int(
        groq_pending
        if groq_pending is not None
        else sot["lanes"][GROQ_REFLECTION_REASONER]["pending_count"]
    )
    s_pending = int(
        sambanova_pending
        if sambanova_pending is not None
        else sot["lanes"][SAMBANOVA_INDEPENDENT_CRITIC]["pending_count"]
    )
    lanes = {
        GROQ_REFLECTION_REASONER: _window_for_profile(
            GROQ_REFLECTION_REASONER,
            pending_count=g_pending,
            retry_after_s=groq_retry_after_s,
            now=now,
        ),
        SAMBANOVA_INDEPENDENT_CRITIC: _window_for_profile(
            SAMBANOVA_INDEPENDENT_CRITIC,
            pending_count=s_pending,
            retry_after_s=sambanova_retry_after_s,
            now=now,
        ),
    }
    any_open = any(v["window_status"] == "OPEN" for v in lanes.values())
    return {
        "schema": SCHEMA_CAPACITY,
        "created_at": _utc(),
        "V2_3_complete": False,
        "lanes": lanes,
        "any_window_open": any_open,
        "ops_may_schedule_observe_only": True,
        "real_resume_authorized": False,
        "provider_lanes": list(PROVIDER_LANES),
        "note": (
            "Capacity windows are ops observability/scheduling hints only; "
            "local Coordinator alone may execute real resume inside an open window."
        ),
    }
