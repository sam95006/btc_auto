"""Real Lesson Prevention gate — fail-closed until V2.3 VERIFIED."""
from __future__ import annotations

from typing import Any

from backend.nexus_lesson_replay_v15.constants import (
    FORBIDDEN_EFFECTS,
    REAL_PROOF_LABEL,
    RISK_STATIC_FIELDS,
    SCHEMA_GATE,
    SOT_TERMINAL_STATUS,
)


def _risk_static() -> dict[str, Any]:
    return {k: False for k in RISK_STATIC_FIELDS} | {
        "exchange_write_attempt_count": 0,
        "mainnet": False,
        "real_money": False,
        "demo_order_count": 0,
    }


def evaluate_real_lesson_gate(
    *,
    v23_terminal_status: str | None,
    v23_complete: bool = False,
    quality_gates_passed: bool = False,
    has_real_bad_process_source: bool = False,
    lesson_retrieved: bool = False,
    measurable_process_change: bool = False,
    repeat_error_prevention: bool = False,
) -> dict[str, Any]:
    """Real Lesson Prevention requires V2.3 VERIFIED + genuine BAD_PROCESS + chain.

    While incomplete: REAL_LESSON_PREVENTION_STATUS=BLOCKED.
    """
    terminal = str(v23_terminal_status or "").upper()
    verified = terminal == "VERIFIED" and bool(v23_complete)
    allowed = (
        verified
        and bool(quality_gates_passed)
        and bool(has_real_bad_process_source)
        and bool(lesson_retrieved)
        and bool(measurable_process_change)
        and bool(repeat_error_prevention)
    )
    if not allowed:
        reason_parts = []
        if not verified:
            reason_parts.append("V2_3_INCOMPLETE")
        if verified and not quality_gates_passed:
            reason_parts.append("QUALITY_GATES_NOT_PASSED")
        if verified and quality_gates_passed and not has_real_bad_process_source:
            reason_parts.append("NO_REAL_BAD_PROCESS_SOURCE")
        if verified and quality_gates_passed and has_real_bad_process_source and not lesson_retrieved:
            reason_parts.append("LESSON_NOT_RETRIEVED")
        if (
            verified
            and quality_gates_passed
            and has_real_bad_process_source
            and lesson_retrieved
            and not measurable_process_change
        ):
            reason_parts.append("NO_MEASURABLE_PROCESS_CHANGE")
        if (
            verified
            and quality_gates_passed
            and has_real_bad_process_source
            and lesson_retrieved
            and measurable_process_change
            and not repeat_error_prevention
        ):
            reason_parts.append("NO_REPEAT_ERROR_PREVENTION")
        return {
            "schema": SCHEMA_GATE,
            "REAL_LESSON_PREVENTION_STATUS": "BLOCKED",
            "policy_effect_lesson_allowed": False,
            "new_policy_effect_lesson_count": 0,
            "blocked_reason": "+".join(reason_parts) or "FAIL_CLOSED",
            "V2_3_terminal_status": terminal or SOT_TERMINAL_STATUS,
            "V2_3_complete": False,
            "quality_gates_passed": bool(quality_gates_passed),
            "has_real_bad_process_source": bool(has_real_bad_process_source),
            "lesson_retrieved": bool(lesson_retrieved),
            "measurable_process_change": bool(measurable_process_change),
            "repeat_error_prevention": bool(repeat_error_prevention),
            "false_learning_claim": False,
            "label": REAL_PROOF_LABEL,
            "fixture_misrepresented_as_real": False,
            **_risk_static(),
        }
    return {
        "schema": SCHEMA_GATE,
        "REAL_LESSON_PREVENTION_STATUS": "READY",
        "policy_effect_lesson_allowed": True,
        "new_policy_effect_lesson_count": 0,
        "blocked_reason": None,
        "V2_3_terminal_status": "VERIFIED",
        "V2_3_complete": True,
        "quality_gates_passed": True,
        "has_real_bad_process_source": True,
        "lesson_retrieved": True,
        "measurable_process_change": True,
        "repeat_error_prevention": True,
        "false_learning_claim": False,
        "label": REAL_PROOF_LABEL,
        "fixture_misrepresented_as_real": False,
        **_risk_static(),
    }


def reject_forbidden_effect(effect: str | None) -> dict[str, Any]:
    e = str(effect or "").strip()
    forbidden = e.lower() in {f.lower() for f in FORBIDDEN_EFFECTS} or e in FORBIDDEN_EFFECTS
    return {
        "requested_effect": e,
        "forbidden": forbidden,
        "deterministic_rejected": forbidden,
        "mutation_applied": False,
        "allowed_to_proceed": not forbidden,
    }
