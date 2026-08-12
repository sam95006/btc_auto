"""Provider queue health — observe incomplete SoT queues without claiming completion."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_ai.profiles import GROQ_REFLECTION_REASONER, SAMBANOVA_INDEPENDENT_CRITIC
from backend.nexus_provider_ops.constants import SCHEMA_QUEUE_HEALTH
from backend.nexus_provider_ops.sot import incomplete_sot_snapshot


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lane_health(
    *,
    profile_id: str,
    success: int,
    pending: int,
    target: int,
    paused: bool = False,
    retry_after_s: float | None = None,
    next_resume_not_before: str | None = None,
    last_exit_reason: str | None = None,
) -> dict[str, Any]:
    total_known = success + pending
    pending_ratio = (pending / total_known) if total_known else 1.0
    if paused:
        status = "PAUSED"
    elif pending <= 0 and success >= target:
        status = "DRAINED"
    elif retry_after_s is not None and float(retry_after_s) > 0:
        status = "RATE_LIMITED"
    elif pending_ratio >= 0.25:
        status = "BACKLOGGED"
    else:
        status = "HEALTHY"
    return {
        "profile_id": profile_id,
        "success_count": int(success),
        "pending_count": int(pending),
        "target_count": int(target),
        "pending_ratio": round(pending_ratio, 6),
        "status": status,
        "manual_paused": bool(paused),
        "retry_after_s": retry_after_s,
        "next_resume_not_before": next_resume_not_before,
        "last_exit_reason": last_exit_reason,
    }


def evaluate_queue_health(
    *,
    groq_success: int | None = None,
    groq_pending: int | None = None,
    sambanova_success: int | None = None,
    sambanova_pending: int | None = None,
    groq_paused: bool = False,
    sambanova_paused: bool = False,
    groq_retry_after_s: float | None = 900.0,
    sambanova_retry_after_s: float | None = 900.0,
    groq_next_resume_not_before: str | None = None,
    sambanova_next_resume_not_before: str | None = None,
) -> dict[str, Any]:
    """Queue health defaults to incomplete SoT counts when overrides omitted."""
    sot = incomplete_sot_snapshot()
    groq_sot = sot["lanes"][GROQ_REFLECTION_REASONER]
    sn_sot = sot["lanes"][SAMBANOVA_INDEPENDENT_CRITIC]

    g_success = int(groq_success if groq_success is not None else groq_sot["success_count"])
    g_pending = int(groq_pending if groq_pending is not None else groq_sot["pending_count"])
    s_success = int(
        sambanova_success if sambanova_success is not None else sn_sot["success_count"]
    )
    s_pending = int(
        sambanova_pending if sambanova_pending is not None else sn_sot["pending_count"]
    )

    lanes = {
        GROQ_REFLECTION_REASONER: _lane_health(
            profile_id=GROQ_REFLECTION_REASONER,
            success=g_success,
            pending=g_pending,
            target=int(groq_sot["target_count"]),
            paused=groq_paused,
            retry_after_s=groq_retry_after_s,
            next_resume_not_before=groq_next_resume_not_before,
            last_exit_reason="PROVIDER_RATE_LIMITED",
        ),
        SAMBANOVA_INDEPENDENT_CRITIC: _lane_health(
            profile_id=SAMBANOVA_INDEPENDENT_CRITIC,
            success=s_success,
            pending=s_pending,
            target=int(sn_sot["target_count"]),
            paused=sambanova_paused,
            retry_after_s=sambanova_retry_after_s,
            next_resume_not_before=sambanova_next_resume_not_before,
            last_exit_reason="PROVIDER_RATE_LIMITED",
        ),
    }
    statuses = {v["status"] for v in lanes.values()}
    if "PAUSED" in statuses:
        overall = "PAUSED"
    elif "RATE_LIMITED" in statuses or "BACKLOGGED" in statuses:
        overall = "DEGRADED_INCOMPLETE"
    elif statuses == {"DRAINED"}:
        overall = "DRAINED"
    else:
        overall = "HEALTHY"

    return {
        "schema": SCHEMA_QUEUE_HEALTH,
        "created_at": _utc(),
        "overall_status": overall,
        "V2_3_complete": False,
        "V2_3_terminal_status": sot["V2_3_terminal_status"],
        "independent_queues": True,
        "lanes": lanes,
        "sot_aligned": (
            g_success == groq_sot["success_count"]
            and g_pending == groq_sot["pending_count"]
            and s_success == sn_sot["success_count"]
            and s_pending == sn_sot["pending_count"]
        ),
    }
