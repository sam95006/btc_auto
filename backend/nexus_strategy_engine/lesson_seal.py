"""Seal prior integration Lessons — not trading knowledge."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_strategy_engine.constants import INTEGRATION_LESSON_STATUSES


def seal_integration_lessons(*, learning_proof_path: Path) -> dict[str, Any]:
    """Mark prior loop Lessons as integration evidence only."""
    if not learning_proof_path.is_file():
        return {
            "schema": "integration_lesson_seal_v1",
            "sealed_count": 0,
            "status": "NO_PRIOR_LEARNING_PROOF",
        }
    proof = json.loads(learning_proof_path.read_text(encoding="utf-8"))
    sealed = {
        "schema": "integration_lesson_seal_v1",
        "source_path": str(learning_proof_path).replace("\\", "/"),
        "lesson_record_count": int(proof.get("lesson_record_count") or 0),
        "lesson_deduplicated_count": int(proof.get("lesson_deduplicated_count") or 0),
        "lesson_conflict_count": int(proof.get("lesson_conflict_count") or 0),
        "undetermined_process_count": int(proof.get("undetermined_process_count") or 0),
        "classification": "INTEGRATION_PROOF_ONLY",
        "alternate_classification": "PROPOSED_INSUFFICIENT_SOURCE_EVIDENCE",
        "allowed_uses": [
            "retrieval_testing",
            "schema_testing",
            "contradiction_testing",
            "ui_demonstration",
            "evidence_quality_development",
        ],
        "forbidden_uses": [
            "alter_strategy_parameters",
            "alter_qualification_thresholds",
            "authorize_demo_orders",
            "become_permanent_policy",
            "validated_trading_knowledge",
            "claim_reduced_future_loss",
        ],
        "may_influence_development_candidates": False,
        "may_influence_qualified_policy": False,
        "statuses_recognized": sorted(INTEGRATION_LESSON_STATUSES),
        "original_provenance_preserved": True,
        "semantic_trade_learning_quality": "CALIBRATION_REQUIRED",
    }
    return sealed


def lesson_may_influence_development(lesson_status: str) -> bool:
    return lesson_status not in INTEGRATION_LESSON_STATUSES and lesson_status not in {
        "REJECTED",
        "REVOKED",
        "PROPOSED",  # insufficient until evidence V2 validated temporary
    }
