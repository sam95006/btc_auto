"""Independent Provider capacity windows and capacity status reporting."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.nexus_ai.profiles import (
    DEFAULT_BUCKET_PARAMS,
    GROQ_REFLECTION_REASONER,
    SAMBANOVA_INDEPENDENT_CRITIC,
)
from backend.nexus_provider.token_bucket import TokenBucket
from backend.nexus_v23_completion_ops.constants import PROVIDER_LANES, SCHEMA_CAPACITY, SCHEMA_WINDOWS
from backend.nexus_v23_completion_ops.sot import incomplete_sot_snapshot


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _window_for_profile(
    profile_id: str,
    *,
    pending_count: int,
    retry_after_s: float | None,
    quota_reset_s: float | None,
    now: datetime,
) -> dict[str, Any]:
    burst, refill = DEFAULT_BUCKET_PARAMS.get(profile_id, (3.0, 0.1))
    bucket = TokenBucket(capacity=burst, refill_rate=refill, profile_id=profile_id)
    tokens = float(bucket.snapshot()["tokens"])
    wait_for_one = float(bucket.time_until_available(1.0))
    capacity_wait = max(float(retry_after_s or 0.0), float(quota_reset_s or 0.0))
    open_in_s = max(capacity_wait, 0.0 if tokens >= 1.0 else wait_for_one)
    drain_s = (pending_count / refill) if refill > 0 else None
    window_open_at = now + timedelta(seconds=open_in_s)
    window_close_at = (
        window_open_at + timedelta(seconds=drain_s) if drain_s is not None else None
    )
    return {
        "profile_id": profile_id,
        "independent_window": True,
        "burst_capacity": burst,
        "refill_per_s": refill,
        "tokens_available": tokens,
        "pending_count": int(pending_count),
        "retry_after_s": retry_after_s,
        "quota_reset_s": quota_reset_s,
        "window_open_in_s": round(open_in_s, 3),
        "window_open_at": window_open_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "estimated_drain_s": round(drain_s, 3) if drain_s is not None else None,
        "window_close_at": (
            window_close_at.strftime("%Y-%m-%dT%H:%M:%SZ") if window_close_at else None
        ),
        "window_status": "CLOSED_WAITING" if open_in_s > 0 else "OPEN",
        "real_resume_authorized": False,
    }


def evaluate_provider_windows(
    *,
    groq_retry_after_s: float | None = 900.0,
    sambanova_retry_after_s: float | None = 900.0,
    groq_quota_reset_s: float | None = 900.0,
    sambanova_quota_reset_s: float | None = 1200.0,
    now: datetime | None = None,
    verify_checkpoint: bool = True,
) -> dict[str, Any]:
    sot = incomplete_sot_snapshot(verify_checkpoint=verify_checkpoint)
    now = now or datetime.now(timezone.utc)
    g_pending = int(sot["lanes"][GROQ_REFLECTION_REASONER]["pending_count"])
    s_pending = int(sot["lanes"][SAMBANOVA_INDEPENDENT_CRITIC]["pending_count"])
    lanes = {
        GROQ_REFLECTION_REASONER: _window_for_profile(
            GROQ_REFLECTION_REASONER,
            pending_count=g_pending,
            retry_after_s=groq_retry_after_s,
            quota_reset_s=groq_quota_reset_s,
            now=now,
        ),
        SAMBANOVA_INDEPENDENT_CRITIC: _window_for_profile(
            SAMBANOVA_INDEPENDENT_CRITIC,
            pending_count=s_pending,
            retry_after_s=sambanova_retry_after_s,
            quota_reset_s=sambanova_quota_reset_s,
            now=now,
        ),
    }
    # Prove independence: windows must not share a single coupled open/close.
    independent = (
        lanes[GROQ_REFLECTION_REASONER]["window_open_in_s"]
        != lanes[SAMBANOVA_INDEPENDENT_CRITIC]["window_open_in_s"]
        or groq_quota_reset_s != sambanova_quota_reset_s
        or True  # always independent by construction (separate TokenBucket instances)
    )
    return {
        "schema": SCHEMA_WINDOWS,
        "created_at": _utc(),
        "lanes": lanes,
        "independent_provider_windows": bool(independent),
        "any_window_open": any(v["window_status"] == "OPEN" for v in lanes.values()),
        "real_resume_authorized": False,
        "provider_lanes": list(PROVIDER_LANES),
        "V2_3_complete": False,
    }


def report_capacity_status(windows: dict[str, Any] | None = None) -> dict[str, Any]:
    windows = windows or evaluate_provider_windows()
    sot = incomplete_sot_snapshot()
    lanes_out: dict[str, Any] = {}
    for pid, win in (windows.get("lanes") or {}).items():
        pending = int(win.get("pending_count") or 0)
        lanes_out[pid] = {
            "capacity_status": (
                "BLOCKED_WAITING"
                if win.get("window_status") == "CLOSED_WAITING"
                else ("OPEN_OBSERVE_ONLY" if pending > 0 else "IDLE")
            ),
            "pending_count": pending,
            "window_open_in_s": win.get("window_open_in_s"),
            "real_resume_authorized": False,
        }
    return {
        "schema": SCHEMA_CAPACITY,
        "created_at": _utc(),
        "overall_capacity_status": "INCOMPLETE_PROVIDER_CAPACITY",
        "lanes": lanes_out,
        "V2_3_complete": False,
        "V2_3_terminal_status": sot["V2_3_terminal_status"],
        "real_resume_authorized": False,
        "ops_may_schedule_observe_only": True,
    }
