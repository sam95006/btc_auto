"""Queue health for incomplete V2.3 SoT — independent Provider queues."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_ai.profiles import GROQ_REFLECTION_REASONER, SAMBANOVA_INDEPENDENT_CRITIC
from backend.nexus_v23_completion_ops.constants import SCHEMA_QUEUE
from backend.nexus_v23_completion_ops.sot import incomplete_sot_snapshot


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
    quota_reset_s: float | None = None,
    next_resume_not_before: str | None = None,
) -> dict[str, Any]:
    total_known = success + pending
    pending_ratio = (pending / total_known) if total_known else 1.0
    if paused:
        status = "PAUSED"
    elif pending <= 0 and success >= target:
        status = "DRAINED"
    elif (retry_after_s is not None and float(retry_after_s) > 0) or (
        quota_reset_s is not None and float(quota_reset_s) > 0
    ):
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
        "quota_reset_s": quota_reset_s,
        "next_resume_not_before": next_resume_not_before,
        "independent_queue": True,
    }


def evaluate_queue_health(
    *,
    groq_paused: bool = False,
    sambanova_paused: bool = False,
    groq_retry_after_s: float | None = 900.0,
    sambanova_retry_after_s: float | None = 900.0,
    groq_quota_reset_s: float | None = None,
    sambanova_quota_reset_s: float | None = None,
    verify_checkpoint: bool = True,
) -> dict[str, Any]:
    sot = incomplete_sot_snapshot(verify_checkpoint=verify_checkpoint)
    groq_sot = sot["lanes"][GROQ_REFLECTION_REASONER]
    sn_sot = sot["lanes"][SAMBANOVA_INDEPENDENT_CRITIC]
    lanes = {
        GROQ_REFLECTION_REASONER: _lane_health(
            profile_id=GROQ_REFLECTION_REASONER,
            success=int(groq_sot["success_count"]),
            pending=int(groq_sot["pending_count"]),
            target=int(groq_sot["target_count"]),
            paused=groq_paused,
            retry_after_s=groq_retry_after_s,
            quota_reset_s=groq_quota_reset_s,
            next_resume_not_before="2026-08-04T16:49:33Z",
        ),
        SAMBANOVA_INDEPENDENT_CRITIC: _lane_health(
            profile_id=SAMBANOVA_INDEPENDENT_CRITIC,
            success=int(sn_sot["success_count"]),
            pending=int(sn_sot["pending_count"]),
            target=int(sn_sot["target_count"]),
            paused=sambanova_paused,
            retry_after_s=sambanova_retry_after_s,
            quota_reset_s=sambanova_quota_reset_s,
            next_resume_not_before="2026-08-04T16:49:58Z",
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
        "schema": SCHEMA_QUEUE,
        "created_at": _utc(),
        "overall_status": overall,
        "V2_3_complete": False,
        "V2_3_terminal_status": sot["V2_3_terminal_status"],
        "independent_queues": True,
        "lanes": lanes,
        "sot_verification": sot.get("verification"),
    }
