"""V10 Reflection Learning Gate — policy-effect Lessons only after V2.3 VERIFIED.

Hard rules:
- No policy-effect Lesson while V2.3 incomplete or failed
- No risk / leverage / size / stop / promotion mutation from this gate
- No profitability claim
- Historical Lesson Prevention Proof is scaffolded only when terminal VERIFIED
"""
from __future__ import annotations

from typing import Any

from backend.nexus_reflection.lesson_gate import apply_lesson_gate, lesson_prevention_allowed

SCHEMA = "v10_reflection_learning_gate_v1"

LEARNING_BLOCKED_INCOMPLETE = "BLOCKED_V2_3_INCOMPLETE"
LEARNING_BLOCKED_FAILED = "BLOCKED_V2_3_FAILED"
LEARNING_SCAFFOLDED = "HISTORICAL_LESSON_PREVENTION_PROOF_SCAFFOLDED"
LEARNING_EXECUTED = "HISTORICAL_LESSON_PREVENTION_PROOF_EXECUTED"
LEARNING_SKIPPED_NO_SOURCE = "HISTORICAL_PROOF_NO_ELIGIBLE_SOURCE"

_RISK_STATIC = {
    "risk_limits_changed": False,
    "leverage_changed": False,
    "position_size_changed": False,
    "stops_changed": False,
    "strategy_parameters_changed": False,
    "promotion_state_changed": False,
    "profitability_claimed": False,
    "exchange_write_attempt_count": 0,
    "mainnet": False,
    "real_money": False,
}


def _terminal_bucket(terminal_status: str | None) -> str:
    t = str(terminal_status or "").upper()
    if t == "VERIFIED":
        return "VERIFIED"
    if t in {"VALID_SAMPLE_QUALITY_FAILED", "FAILED", "QUALITY_FAILED"}:
        return "FAILED"
    return "INCOMPLETE"


def evaluate_learning_gate(
    *,
    terminal_status: str | None,
    quality_gates_passed: bool = False,
) -> dict[str, Any]:
    """Fail-closed gate: policy-effect Lessons require VERIFIED + quality pass."""
    bucket = _terminal_bucket(terminal_status)
    allowed = lesson_prevention_allowed(terminal_status) and bool(quality_gates_passed)
    # Never pass VERIFIED into apply_lesson_gate unless both terminal + quality pass.
    base = apply_lesson_gate(
        terminal_status="VERIFIED" if allowed else (terminal_status if bucket != "VERIFIED" else "INCOMPLETE"),
        proposed_lesson_count=0,
    )
    if not allowed:
        status = LEARNING_BLOCKED_FAILED if bucket == "FAILED" else LEARNING_BLOCKED_INCOMPLETE
        return {
            "schema": SCHEMA,
            "learning_prevention_status": status,
            "policy_effect_lesson_allowed": False,
            "new_policy_effect_lesson_count": 0,
            "false_learning_claim": False,
            "V2_3_terminal_status": terminal_status,
            "quality_gates_passed": bool(quality_gates_passed),
            **_RISK_STATIC,
            "lesson_gate": {
                **base,
                "new_policy_effect_lesson_count": 0,
                "lesson_prevention_executed": False,
                "lesson_prevention_blocked_reason": (
                    "V2_3_QUALITY_NOT_PASSED"
                    if lesson_prevention_allowed(terminal_status) and not quality_gates_passed
                    else base.get("lesson_prevention_blocked_reason")
                ),
            },
        }
    return {
        "schema": SCHEMA,
        "learning_prevention_status": "READY_FOR_HISTORICAL_PROOF",
        "policy_effect_lesson_allowed": True,
        "new_policy_effect_lesson_count": 0,
        "false_learning_claim": False,
        "V2_3_terminal_status": "VERIFIED",
        "quality_gates_passed": True,
        **_RISK_STATIC,
        "lesson_gate": base,
    }


def scaffold_historical_lesson_prevention_proof(
    *,
    terminal_status: str | None,
    quality_gates_passed: bool,
    packets: list[dict[str, Any]] | None = None,
    execute: bool = False,
    use_real_ai: bool = False,
) -> dict[str, Any]:
    """Scaffold (and optionally execute) historical Lesson Prevention Proof.

    Never claims profitability. Does not mutate risk. When V2.3 is incomplete,
    returns a blocked scaffold with zero policy-effect lessons.
    """
    gate = evaluate_learning_gate(
        terminal_status=terminal_status,
        quality_gates_passed=quality_gates_passed,
    )
    if not gate["policy_effect_lesson_allowed"]:
        return {
            **gate,
            "proof_scaffold": {
                "proof_level": "REAL_HISTORICAL_CHAIN_PROOF",
                "status": "NOT_EXECUTED",
                "reason": gate["learning_prevention_status"],
                "profitability_claimed": False,
                "label": "BLOCKED_UNTIL_V2_3_VERIFIED",
            },
        }

    scaffold: dict[str, Any] = {
        "proof_level": "REAL_HISTORICAL_CHAIN_PROOF",
        "status": "SCAFFOLDED",
        "reason": None,
        "profitability_claimed": False,
        "label": "HISTORICAL_LESSON_PREVENTION_PROOF_ONLY",
        "claims": {
            "profitability": False,
            "edge_proven": False,
            "strategy_promotion": False,
            "real_trading_learning": False,
        },
        "allowed_effects_only": True,
        "forbidden_risk_mutations": True,
    }
    out = {
        **gate,
        "learning_prevention_status": LEARNING_SCAFFOLDED,
        "proof_scaffold": scaffold,
    }
    if not execute:
        return out

    from backend.nexus_edge_discovery.learning_prevention_proof import (
        run_learning_prevention_proof,
    )

    proof = run_learning_prevention_proof(
        packets=list(packets or []),
        use_real_ai=use_real_ai,
        proof_level="REAL_HISTORICAL_CHAIN_PROOF",
    )
    lesson_count = int(proof.get("new_policy_effect_lesson_count") or proof.get("lesson_created_count") or 0)
    status = str(
        proof.get("real_historical_chain_proof_status")
        or proof.get("REAL_HISTORICAL_CHAIN_PROOF")
        or ""
    )
    if status in {"NO_ELIGIBLE_BAD_PROCESS_SOURCE", "SKIPPED", "SKIPPED_QUALITY_GATES_NOT_PASSED"}:
        learning_status = LEARNING_SKIPPED_NO_SOURCE
        lesson_count = 0
    else:
        learning_status = LEARNING_EXECUTED

    scaffold["status"] = "EXECUTED"
    scaffold["proof_result_status"] = status
    scaffold["proof_summary"] = {
        "bad_process_source_count": proof.get("bad_process_source_count"),
        "lesson_created_count": proof.get("lesson_created_count"),
        "new_policy_effect_lesson_count": lesson_count,
        "hard_risk_static_ban_status": proof.get("hard_risk_static_ban_status"),
        "misrepresented_as_real_learning": bool(proof.get("misrepresented_as_real_learning")),
        "profitability_claimed": False,
    }
    return {
        **out,
        "learning_prevention_status": learning_status,
        "new_policy_effect_lesson_count": lesson_count if learning_status == LEARNING_EXECUTED else 0,
        "proof_scaffold": scaffold,
        "proof_result": proof,
        "false_learning_claim": bool(proof.get("misrepresented_as_real_learning")),
    }
