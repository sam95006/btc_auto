"""Canonical incomplete checkpoint SoT for V13-B — trust checkpoint counters, not summaries."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_ai.profiles import GROQ_REFLECTION_REASONER, SAMBANOVA_INDEPENDENT_CRITIC
from backend.nexus_v23_completion_ops.constants import (
    CANONICAL_CHECKPOINT_PATH,
    SCHEMA,
    SOT_CASE_COUNT,
    SOT_GROQ_PENDING,
    SOT_GROQ_SUCCESS,
    SOT_GROQ_TARGET,
    SOT_SAMBANOVA_PENDING,
    SOT_SAMBANOVA_SUCCESS,
    SOT_TERMINAL_STATUS,
    SOT_V2_3_COMPLETE,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_checkpoint_counters_only(path: Path | str | None = None) -> dict[str, Any]:
    """Read ONLY safe counter fields from a checkpoint. Never returns secret-bearing blobs."""
    target = Path(path) if path else Path(CANONICAL_CHECKPOINT_PATH)
    if not target.is_file():
        return {
            "checkpoint_available": False,
            "checkpoint_path": str(target),
            "read_status": "MISSING",
        }
    try:
        state = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "checkpoint_available": True,
            "checkpoint_path": str(target),
            "read_status": f"ERROR:{type(exc).__name__}",
        }
    if not isinstance(state, dict):
        return {
            "checkpoint_available": True,
            "checkpoint_path": str(target),
            "read_status": "INVALID_TYPE",
        }
    transport = state.get("transport") or {}
    groq = transport.get(GROQ_REFLECTION_REASONER) or {}
    sn = transport.get(SAMBANOVA_INDEPENDENT_CRITIC) or {}
    return {
        "checkpoint_available": True,
        "checkpoint_path": str(target),
        "read_status": "OK",
        "schema": state.get("schema"),
        "schema_version": state.get("schema_version"),
        "case_id_count": len(state.get("case_ids") or []),
        "completed_case_count": len(state.get("completed_case_ids") or []),
        "pending_case_count": len(state.get("pending_case_ids") or []),
        "critic_resolved_count": len(state.get("critic_resolved_ids") or []),
        "critic_pending_count": len(
            state.get("critic_pending_ids") or state.get("pending_critic_case_ids") or []
        ),
        "groq_success_count": int(groq.get("success_count") or 0),
        "groq_429_count": int(groq.get("HTTP_429_count") or 0),
        "groq_next_resume_not_before": groq.get("next_resume_not_before"),
        "groq_quota_reset_at": groq.get("quota_reset_at"),
        "sambanova_success_count": int(sn.get("success_count") or 0),
        "sambanova_429_count": int(sn.get("HTTP_429_count") or 0),
        "sambanova_next_resume_not_before": sn.get("next_resume_not_before"),
        "sambanova_quota_reset_at": sn.get("quota_reset_at"),
        "rebuilt_from_summary_metrics": False,
        "secret_fields_exported": False,
    }


def incomplete_sot_snapshot(*, verify_checkpoint: bool = True) -> dict[str, Any]:
    """Frozen incomplete SoT used by ops — never a fabricated completion claim."""
    verification: dict[str, Any] = {"verified": False, "source": "constants_approx"}
    g_success, g_pending = SOT_GROQ_SUCCESS, SOT_GROQ_PENDING
    s_success, s_pending = SOT_SAMBANOVA_SUCCESS, SOT_SAMBANOVA_PENDING
    case_count = SOT_CASE_COUNT

    if verify_checkpoint:
        counters = read_checkpoint_counters_only()
        if counters.get("read_status") == "OK":
            # Trust checkpoint over approximate constants / summaries.
            g_success = int(counters["groq_success_count"])
            g_pending = int(counters["pending_case_count"])
            s_success = int(counters["sambanova_success_count"])
            s_pending = int(counters["critic_pending_count"])
            case_count = int(counters["case_id_count"]) or SOT_CASE_COUNT
            verification = {
                "verified": True,
                "source": "canonical_checkpoint_counters",
                "checkpoint_path": counters.get("checkpoint_path"),
                "matches_approx_constants": (
                    g_success == SOT_GROQ_SUCCESS
                    and g_pending == SOT_GROQ_PENDING
                    and s_success == SOT_SAMBANOVA_SUCCESS
                    and s_pending == SOT_SAMBANOVA_PENDING
                ),
            }
        else:
            verification = {
                "verified": False,
                "source": "constants_approx_fallback",
                "checkpoint_read": counters,
            }

    return {
        "schema": f"{SCHEMA}_incomplete_sot",
        "created_at": _utc(),
        "V2_3_complete": SOT_V2_3_COMPLETE,
        "V2_3_terminal_status": SOT_TERMINAL_STATUS,
        "case_id_count": case_count,
        "groq_target_count": SOT_GROQ_TARGET,
        "lanes": {
            GROQ_REFLECTION_REASONER: {
                "success_count": g_success,
                "pending_count": g_pending,
                "target_count": SOT_GROQ_TARGET,
                "completion_ratio": g_success / max(1, SOT_GROQ_TARGET),
            },
            SAMBANOVA_INDEPENDENT_CRITIC: {
                "success_count": s_success,
                "pending_count": s_pending,
                "target_count": g_success,
                "completion_ratio": s_success / max(1, g_success),
            },
        },
        "verification": verification,
        "note": (
            "Real checkpoint SoT remains incomplete; ops observe and control around "
            "this truth and must not claim V2.3 complete."
        ),
    }


def assert_incomplete_truth(report: dict[str, Any]) -> None:
    """Fail closed if a report falsely claims V2.3 complete."""
    if report.get("V2_3_complete") is True:
        raise RuntimeError("V2_3_complete_claim_banned")
    status = str(report.get("V2_3_terminal_status") or "").upper()
    if status in {"VERIFIED", "COMPLETE", "PASSED", "V2_3_COMPLETE"}:
        raise RuntimeError(f"V2_3_complete_status_banned:{status}")


def synthetic_incomplete_checkpoint() -> dict[str, Any]:
    """Sanitized fixture checkpoint matching incomplete SoT (Background Agent only)."""
    completed = [f"case_{i:03d}" for i in range(SOT_GROQ_SUCCESS)]
    pending = [f"case_{i:03d}" for i in range(SOT_GROQ_SUCCESS, SOT_GROQ_SUCCESS + SOT_GROQ_PENDING)]
    critic_resolved = completed[:SOT_SAMBANOVA_SUCCESS]
    critic_pending = completed[SOT_SAMBANOVA_SUCCESS : SOT_SAMBANOVA_SUCCESS + SOT_SAMBANOVA_PENDING]
    return {
        "schema": "blind_reflection_v23_checkpoint_v4_fixture",
        "schema_version": 4,
        "fixture_label": "CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING",
        "case_ids": [f"case_{i:03d}" for i in range(SOT_CASE_COUNT)],
        "completed_case_ids": completed,
        "pending_case_ids": pending,
        "critic_resolved_ids": critic_resolved,
        "critic_pending_ids": critic_pending,
        "pending_critic_case_ids": critic_pending,
        "critic_case_ids": critic_resolved + critic_pending,
        "transport": {
            GROQ_REFLECTION_REASONER: {
                "profile_id": GROQ_REFLECTION_REASONER,
                "success_count": SOT_GROQ_SUCCESS,
                "HTTP_429_count": 20,
                "retry_after": 900,
                "next_resume_not_before": "2026-08-04T16:49:33Z",
                "quota_reset_at": None,
                "last_exit_reason": "PROVIDER_RATE_LIMITED",
            },
            SAMBANOVA_INDEPENDENT_CRITIC: {
                "profile_id": SAMBANOVA_INDEPENDENT_CRITIC,
                "success_count": SOT_SAMBANOVA_SUCCESS,
                "HTTP_429_count": 17,
                "retry_after": 900,
                "next_resume_not_before": "2026-08-04T16:49:58Z",
                "quota_reset_at": None,
                "last_exit_reason": "PROVIDER_RATE_LIMITED",
            },
        },
        "stage": "PROVIDER_CAPACITY_BLOCKED",
        "exit_reason": "PROVIDER_RATE_LIMITED",
        "V2_3_complete": False,
        "V2_3_terminal_status": SOT_TERMINAL_STATUS,
    }
