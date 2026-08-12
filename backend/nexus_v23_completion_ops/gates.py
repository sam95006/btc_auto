"""Terminal denominator validation + lesson/quality gates while incomplete."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_edge_discovery.ratio_metrics import make_ratio
from backend.nexus_reflection.lesson_gate_v11 import apply_lesson_gate_v11
from backend.nexus_reflection.terminal_eval import evaluate_terminal, validate_terminal_denominators
from backend.nexus_v23_completion_ops.constants import (
    SCHEMA_GATES,
    SCHEMA_TERMINAL,
    SOT_TERMINAL_STATUS,
)
from backend.nexus_v23_completion_ops.sot import assert_incomplete_truth, synthetic_incomplete_checkpoint


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def assert_quality_eval_blocked(state: dict[str, Any] | None = None) -> None:
    """Hard ban helper: raise if quality gates evaluate before complete denominators."""
    state = state or synthetic_incomplete_checkpoint()
    terminal = evaluate_terminal(state)
    if bool(terminal.get("quality_gates_evaluated")) or bool(terminal.get("quality_gates_passed")):
        raise RuntimeError("quality_eval_before_complete_denominators_banned")
    if str(terminal.get("V2_3_TERMINAL_STATUS") or "").upper() in {"VERIFIED", "COMPLETE"}:
        raise RuntimeError("V2_3_complete_claim_banned")


def evaluate_terminal_denominators_ops(state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate terminal denominators on incomplete fixture; quality must stay blocked."""
    state = state or synthetic_incomplete_checkpoint()
    assert_quality_eval_blocked(state)
    terminal = evaluate_terminal(state)
    denom = validate_terminal_denominators(terminal)
    # Explicit incomplete-denominator probe
    incomplete_quality = {
        "full_calibration_completion_ratio": make_ratio(53, 80),
        "critic_resolution_ratio": make_ratio(16, 53),
        "zero_ready_ratio": make_ratio(0, 0),  # must be NOT_APPLICABLE
    }
    zero_probe = validate_terminal_denominators(incomplete_quality)
    # Fake complete-denominator claim while incomplete must still fail closed.
    fake_complete = {
        "full_calibration_completion_ratio": make_ratio(80, 80),
        "critic_resolution_ratio": make_ratio(80, 80),
    }
    # Denominator math may look complete, but terminal eval on incomplete SoT must block quality.
    quality_evaluated = bool(terminal.get("quality_gates_evaluated"))
    report = {
        "schema": SCHEMA_TERMINAL,
        "created_at": _utc(),
        "terminal_eval": {
            "V2_3_TERMINAL_STATUS": terminal.get("V2_3_TERMINAL_STATUS"),
            "quality_gates_evaluated": quality_evaluated,
            "quality_gates_passed": bool(terminal.get("quality_gates_passed")),
        },
        "denominator_validation": denom,
        "zero_denominator_probe": zero_probe,
        "fake_complete_ratios_ignored": True,
        "fake_complete_ratio_probe": fake_complete,
        "quality_eval_blocked_while_incomplete": quality_evaluated is False,
        "V2_3_complete": False,
        "V2_3_terminal_status": SOT_TERMINAL_STATUS,
    }
    assert_incomplete_truth(report)
    if quality_evaluated:
        raise RuntimeError("quality_eval_before_complete_denominators_banned")
    return report


def evaluate_lesson_quality_gates(
    *,
    terminal_status: str | None = None,
    quality_gates_passed: bool = False,
) -> dict[str, Any]:
    """Block policy-effect lessons and quality claims while V2.3 incomplete."""
    status = terminal_status or SOT_TERMINAL_STATUS
    lesson = apply_lesson_gate_v11(
        terminal_status=status,
        quality_gates_passed=quality_gates_passed,
        proposed_policy_effect_lesson_count=3,
        fixture_label="CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING",
    )
    # Also prove non-fixture incomplete still blocks policy-effect lessons.
    incomplete_live = apply_lesson_gate_v11(
        terminal_status=status,
        quality_gates_passed=False,
        proposed_policy_effect_lesson_count=2,
        fixture_label=None,
    )
    report = {
        "schema": SCHEMA_GATES,
        "created_at": _utc(),
        "fixture_lesson_gate": lesson,
        "incomplete_lesson_gate": incomplete_live,
        "policy_effect_lesson_allowed": False,
        "policy_effect_blocked": (
            lesson.get("policy_effect_lesson_allowed") is False
            and incomplete_live.get("policy_effect_lesson_allowed") is False
        ),
        "new_policy_effect_lesson_count": 0,
        "quality_eval_allowed": False,
        "V2_3_complete": False,
        "V2_3_terminal_status": status,
    }
    if lesson.get("new_policy_effect_lesson_count", 0) != 0:
        raise RuntimeError("policy_effect_lessons_while_incomplete_banned")
    if incomplete_live.get("new_policy_effect_lesson_count", 0) != 0:
        raise RuntimeError("policy_effect_lessons_while_incomplete_banned")
    assert_incomplete_truth(report)
    return report
