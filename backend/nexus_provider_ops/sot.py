"""Canonical incomplete checkpoint Source-of-Truth for V12-C ops.

Real checkpoint SoT remains incomplete (Groq 53/27, SambaNova critic 16/10).
Ops MUST design around this truth and never claim V2.3 complete.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_ai.profiles import GROQ_REFLECTION_REASONER, SAMBANOVA_INDEPENDENT_CRITIC
from backend.nexus_provider_ops.constants import (
    SCHEMA,
    SOT_CASE_COUNT,
    SOT_GROQ_PENDING,
    SOT_GROQ_SUCCESS,
    SOT_SAMBANOVA_PENDING,
    SOT_SAMBANOVA_SUCCESS,
    SOT_TERMINAL_STATUS,
    SOT_V2_3_COMPLETE,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def incomplete_sot_snapshot() -> dict[str, Any]:
    """Frozen incomplete SoT used by ops — not a fabricated completion claim."""
    return {
        "schema": f"{SCHEMA}_incomplete_sot",
        "created_at": _utc(),
        "V2_3_complete": SOT_V2_3_COMPLETE,
        "V2_3_terminal_status": SOT_TERMINAL_STATUS,
        "case_id_count": SOT_CASE_COUNT,
        "lanes": {
            GROQ_REFLECTION_REASONER: {
                "success_count": SOT_GROQ_SUCCESS,
                "pending_count": SOT_GROQ_PENDING,
                "target_count": SOT_CASE_COUNT,
                "completion_ratio": SOT_GROQ_SUCCESS / SOT_CASE_COUNT,
            },
            SAMBANOVA_INDEPENDENT_CRITIC: {
                "success_count": SOT_SAMBANOVA_SUCCESS,
                "pending_count": SOT_SAMBANOVA_PENDING,
                "target_count": SOT_GROQ_SUCCESS,  # critic follows reasoner successes
                "completion_ratio": SOT_SAMBANOVA_SUCCESS / max(1, SOT_GROQ_SUCCESS),
            },
        },
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
