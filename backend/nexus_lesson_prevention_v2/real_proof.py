"""Real policy-effect Lesson Prevention proof — blocked while V2.3 incomplete."""
from __future__ import annotations

from typing import Any

from backend.nexus_lesson_prevention_v2.constants import (
    REAL_PROOF_LABEL,
    SCHEMA_REAL,
)
from backend.nexus_lesson_prevention_v2.gate import evaluate_real_lesson_gate


def run_real_policy_effect_proof(
    *,
    checkpoint: dict[str, Any],
    real_bad_process_packets: list[dict[str, Any]] | None = None,
    quality_gates_passed: bool = False,
) -> dict[str, Any]:
    """Attempt real proof only when V2.3 VERIFIED + real BAD_PROCESS source.

    Fixtures are explicitly excluded. While incomplete → BLOCKED.
    """
    real_packets = [
        p
        for p in (real_bad_process_packets or [])
        if not p.get("is_fixture")
        and p.get("control_fixture_label") != "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE"
        and not str(p.get("trade_id") or "").startswith(("CAL_V21_FIX", "CAL_V23_FIX", "V14G_FIX"))
    ]
    gate = evaluate_real_lesson_gate(
        v23_terminal_status=checkpoint.get("V2_3_terminal_status"),
        v23_complete=bool(checkpoint.get("V2_3_complete")),
        quality_gates_passed=quality_gates_passed,
        has_real_bad_process_source=len(real_packets) > 0,
    )
    if gate["REAL_LESSON_PREVENTION_STATUS"] == "BLOCKED":
        return {
            "schema": SCHEMA_REAL,
            "label": REAL_PROOF_LABEL,
            "REAL_LESSON_PREVENTION_STATUS": "BLOCKED",
            "real_policy_effect_proof_status": "BLOCKED",
            "blocked_reason": gate.get("blocked_reason"),
            "new_policy_effect_lesson_count": 0,
            "genuine_bad_process_source_trade_count": len(real_packets),
            "fixture_used_as_real_proof": False,
            "misrepresented_as_real_learning": False,
            "requirements": {
                "v23_terminal_verified": False,
                "real_bad_process_case": len(real_packets) > 0,
                "retrieved_lesson": False,
                "measurable_change": False,
                "no_risk_mutation_outside_scope": True,
                "no_repeated_material_process_error": True,
            },
            "gate": gate,
        }

    # Ready path is scaffolded only — this lane does not invent real historical sources.
    return {
        "schema": SCHEMA_REAL,
        "label": REAL_PROOF_LABEL,
        "REAL_LESSON_PREVENTION_STATUS": "READY_SCAFFOLD_ONLY",
        "real_policy_effect_proof_status": "NOT_EXECUTED_NO_AUTHORIZING_SOURCE_IN_LANE",
        "new_policy_effect_lesson_count": 0,
        "genuine_bad_process_source_trade_count": len(real_packets),
        "fixture_used_as_real_proof": False,
        "misrepresented_as_real_learning": False,
        "gate": gate,
        "note": "Execution of real chain deferred to authorizing Coordinator after V2.3 VERIFIED",
    }
