"""V11 lesson gate enforcement for Reflection V2.3 adjudication."""
from __future__ import annotations

from typing import Any

CONTROL_FIXTURE_LABEL = "CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING"


def policy_effect_lessons_allowed(
    *,
    terminal_status: str | None,
    quality_gates_passed: bool,
    fixture_label: str | None = None,
) -> bool:
    """Allow policy-effect lessons only after verified, non-fixture V2.3 completion."""
    if str(fixture_label or "") == CONTROL_FIXTURE_LABEL:
        return False
    return str(terminal_status or "").upper() == "VERIFIED" and bool(quality_gates_passed)


def apply_lesson_gate_v11(
    *,
    terminal_status: str | None,
    quality_gates_passed: bool = False,
    proposed_policy_effect_lesson_count: int = 0,
    fixture_label: str | None = None,
) -> dict[str, Any]:
    allowed = policy_effect_lessons_allowed(
        terminal_status=terminal_status,
        quality_gates_passed=quality_gates_passed,
        fixture_label=fixture_label,
    )
    count = int(proposed_policy_effect_lesson_count) if allowed else 0
    reason = None
    if not allowed:
        reason = (
            "CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING"
            if str(fixture_label or "") == CONTROL_FIXTURE_LABEL
            else "V2_3_TERMINAL_NOT_VERIFIED"
        )
    return {
        "lesson_gate_schema": "v11_lesson_gate",
        "policy_effect_lesson_allowed": allowed,
        "lesson_prevention_executed": allowed,
        "lesson_prevention_blocked_reason": reason,
        "V2_3_TERMINAL_STATUS": terminal_status,
        "quality_gates_passed": bool(quality_gates_passed),
        "fixture_label": fixture_label,
        "new_policy_effect_lesson_count": count,
        "risk_limits_changed": False,
        "leverage_changed": False,
        "position_size_changed": False,
        "stops_changed": False,
        "strategy_parameters_changed": False,
        "promotion_state_changed": False,
        "false_learning_claim": False,
    }
