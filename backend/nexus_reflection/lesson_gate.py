"""Real Lesson Prevention gate — only when V2_3_TERMINAL_STATUS=VERIFIED."""
from __future__ import annotations

from typing import Any


def lesson_prevention_allowed(terminal_status: str | None) -> bool:
    return str(terminal_status or "").upper() == "VERIFIED"


def apply_lesson_gate(
    *,
    terminal_status: str | None,
    proposed_lesson_count: int = 0,
) -> dict[str, Any]:
    """Block real lesson writes unless terminal VERIFIED. Never mutates risk/leverage."""
    allowed = lesson_prevention_allowed(terminal_status)
    if not allowed:
        return {
            "lesson_prevention_executed": False,
            "lesson_prevention_blocked_reason": "V2_3_TERMINAL_NOT_VERIFIED",
            "V2_3_TERMINAL_STATUS": terminal_status,
            "new_policy_effect_lesson_count": 0,
            "risk_limits_changed": False,
            "leverage_changed": False,
            "position_size_changed": False,
            "stops_changed": False,
            "strategy_parameters_changed": False,
            "promotion_state_changed": False,
        }
    return {
        "lesson_prevention_executed": True,
        "lesson_prevention_blocked_reason": None,
        "V2_3_TERMINAL_STATUS": "VERIFIED",
        "new_policy_effect_lesson_count": int(proposed_lesson_count),
        "risk_limits_changed": False,
        "leverage_changed": False,
        "position_size_changed": False,
        "stops_changed": False,
        "strategy_parameters_changed": False,
        "promotion_state_changed": False,
    }


RECOMMENDATIONS = (
    "NEXUS_REFLECTION_V23_TERMINAL_VERIFIED",
    "NEXUS_REFLECTION_V23_PARTIAL_PROVIDER_CAPACITY",
    "NEXUS_REFLECTION_V23_LOCAL_CHECKPOINT_REQUIRED",
    "NEXUS_REFLECTION_V23_VALID_SAMPLE_QUALITY_FAILED",
    "NEXUS_REFLECTION_V23_CHECKPOINT_INVALID",
    "NEXUS_REFLECTION_V23_IMPLEMENTATION_INVALID",
)


def pick_agent_c_recommendation(
    *,
    impl_ok: bool,
    local_checkpoint_available: bool,
    checkpoint_integrity_ok: bool | None,
    real_resume_executed: bool,
    terminal_status: str | None,
    quality_evaluated: bool,
    quality_passed: bool,
) -> str:
    if not impl_ok:
        return "NEXUS_REFLECTION_V23_IMPLEMENTATION_INVALID"
    if not local_checkpoint_available:
        return "NEXUS_REFLECTION_V23_LOCAL_CHECKPOINT_REQUIRED"
    if checkpoint_integrity_ok is False:
        return "NEXUS_REFLECTION_V23_CHECKPOINT_INVALID"
    if quality_evaluated and not quality_passed:
        return "NEXUS_REFLECTION_V23_VALID_SAMPLE_QUALITY_FAILED"
    if str(terminal_status or "").upper() == "VERIFIED" and quality_passed:
        return "NEXUS_REFLECTION_V23_TERMINAL_VERIFIED"
    if not real_resume_executed and local_checkpoint_available:
        # Available but this isolated agent did not run real resume
        return "NEXUS_REFLECTION_V23_PARTIAL_PROVIDER_CAPACITY"
    return "NEXUS_REFLECTION_V23_PARTIAL_PROVIDER_CAPACITY"
