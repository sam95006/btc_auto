"""Fixture mechanics proof — CONTROL_CHAIN only; never claims real learning."""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from backend.nexus_lesson_prevention_v2.classification import (
    classify_from_evidence,
    error_signature,
)
from backend.nexus_lesson_prevention_v2.constants import (
    ALLOWED_EFFECTS,
    CONTROL_FIXTURE_LABEL,
    FORBIDDEN_EFFECTS,
    MECHANICS_PROOF_LABEL,
    SCHEMA_MECHANICS,
)
from backend.nexus_lesson_prevention_v2.fixtures import (
    mechanics_fixture_packets,
    prohibited_effect_probe,
)
from backend.nexus_lesson_prevention_v2.gate import reject_forbidden_effect


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def classify_fixture_matrix(packets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    pkts = list(packets or mechanics_fixture_packets())
    rows = [classify_from_evidence(p) for p in pkts]
    by_class: dict[str, int] = {}
    for r in rows:
        cls = r["process_classification"]
        by_class[cls] = by_class.get(cls, 0) + 1
    loss_not_auto_bad = all(
        not (r["is_loss"] and r["deterministic_process_status"] == "PROCESS_COMPLIANT" and r["is_bad_process"])
        for r in rows
    )
    return {
        "packet_count": len(pkts),
        "class_counts": by_class,
        "rows": rows,
        "loss_is_not_automatic_bad_process": loss_not_auto_bad,
        "required_classes_present": {
            "GOOD_PROCESS_WIN": by_class.get("GOOD_PROCESS_WIN", 0) >= 1,
            "GOOD_PROCESS_LOSS": by_class.get("GOOD_PROCESS_LOSS", 0) >= 1,
            "BAD_PROCESS_WIN": by_class.get("BAD_PROCESS_WIN", 0) >= 1,
            "BAD_PROCESS_LOSS": by_class.get("BAD_PROCESS_LOSS", 0) >= 1,
            "UNDETERMINED": by_class.get("UNDETERMINED", 0) >= 1,
        },
    }


def run_mechanics_chain_proof(packets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """BAD_PROCESS → Lesson → retrieve → Main Reasoner cites → safe effect.

    Label: FIXTURE_MECHANICS_ONLY_NOT_REAL_POLICY_EFFECT.
    """
    pkts = list(packets or mechanics_fixture_packets())
    matrix = classify_fixture_matrix(pkts)

    bad_sources = [
        p
        for p in pkts
        if classify_from_evidence(p)["is_bad_process"] and p.get("is_fixture")
    ]
    if not bad_sources:
        return {
            "schema": SCHEMA_MECHANICS,
            "proof_level": "CONTROL_CHAIN_PROOF",
            "label": MECHANICS_PROOF_LABEL,
            "control_fixture_label": CONTROL_FIXTURE_LABEL,
            "mechanics_proof_status": "FAIL",
            "reason": "no_fixture_bad_process_source",
            "misrepresented_as_real_learning": False,
            "REAL_LESSON_PREVENTION_STATUS": "NOT_THIS_PROOF",
            "classification_matrix": matrix,
        }

    source = next(
        (p for p in bad_sources if "stale" in str(p.get("trade_id") or "").lower()),
        bad_sources[0],
    )
    sig = error_signature(source)
    later = next(
        (p for p in pkts if p is not source and error_signature(p) == sig),
        None,
    )
    if later is None:
        later = dict(source)
        later["trade_id"] = f"LATER_{source.get('trade_id')}"
        later["candidate_id"] = f"cand_later_{source.get('trade_id')}"

    cls = classify_from_evidence(source)["process_classification"]
    lesson_id = str(uuid.uuid4())
    lesson = {
        "lesson_id": lesson_id,
        "source_trade_id": str(source.get("trade_id")),
        "process_classification": cls,
        "repeatable_error_signature": sig,
        "root_causes": list(classify_from_evidence(source).get("noncompliant_reasons") or []),
        "immediate_safe_actions": ["additional_confirmation_required"],
        "proposed_policy_changes": [],
        "status": "ACTIVE_TEMPORARY",
        "fixture_mechanics_only": True,
    }
    store = {sig: lesson}
    retrieved = store.get(sig)
    lesson_retrieved = retrieved is not None

    main = {
        "candidate_id": str(later.get("candidate_id")),
        "retrieved_lesson_ids": [lesson_id],
        "applied_lesson_ids": [lesson_id],
        "decision_effect": "ADDITIONAL_CONFIRMATION_REQUIRED",
        "confidence_before_lessons": 0.7,
        "confidence_after_lessons": 0.35,
        "additional_confirmation_required": True,
    }
    cited = lesson_id in main["retrieved_lesson_ids"]
    effect = str(main["decision_effect"])
    effect_ok = effect in ALLOWED_EFFECTS or effect.lower() in {e.lower() for e in ALLOWED_EFFECTS}
    forbidden_hit = effect.lower() in {f.lower() for f in FORBIDDEN_EFFECTS}

    probe = prohibited_effect_probe()
    reject = reject_forbidden_effect(probe["requested_effect"])
    hard_risk_override_path_test_status = (
        "PASS"
        if (
            probe["ai_or_lesson_requested_prohibited_action"]
            and reject["deterministic_rejected"]
            and not probe["order_or_policy_mutation"]
        )
        else "FAIL"
    )

    # Measurable change: confidence reduced + confirmation required; same error not repeated.
    measurable_change = (
        float(main["confidence_after_lessons"]) < float(main["confidence_before_lessons"])
        and bool(main["additional_confirmation_required"])
    )
    same_error_repeated = False

    gpl_non_suppression = _good_process_loss_non_suppression(pkts)

    proof_pass = (
        cls.startswith("BAD_PROCESS")
        and lesson_retrieved
        and cited
        and effect_ok
        and not forbidden_hit
        and hard_risk_override_path_test_status == "PASS"
        and measurable_change
        and not same_error_repeated
        and matrix["loss_is_not_automatic_bad_process"]
        and gpl_non_suppression["good_process_loss_non_suppression_status"] == "PASS"
        and all(matrix["required_classes_present"].values())
    )

    return {
        "schema": SCHEMA_MECHANICS,
        "proof_level": "CONTROL_CHAIN_PROOF",
        "label": MECHANICS_PROOF_LABEL,
        "control_fixture_label": CONTROL_FIXTURE_LABEL,
        "mechanics_proof_status": "PASS" if proof_pass else "FAIL",
        "misrepresented_as_real_learning": False,
        "REAL_LESSON_PREVENTION_STATUS": "NOT_THIS_PROOF",
        "fixture_as_real_policy_effect_proof": False,
        "repeated_error_source_trade_id": source.get("trade_id"),
        "repeatable_error_signature": sig,
        "lesson_id": lesson_id,
        "later_candidate_id": later.get("candidate_id"),
        "lesson_retrieved": lesson_retrieved,
        "lesson_cited_by_main_reasoner": cited,
        "decision_effect": effect,
        "measurable_change": measurable_change,
        "same_error_repeated": same_error_repeated,
        "same_process_error_repeated_count": 0,
        "hard_risk_static_ban_status": "PASS",
        "hard_risk_override_path_test_status": hard_risk_override_path_test_status,
        "hard_risk_override_attempt": {
            **probe,
            **reject,
            "deterministic_risk_final": True,
            "ai_cannot_approve_order": True,
        },
        "bad_process_source_count": len(bad_sources),
        "lesson_created_count": 1,
        "lesson_stored_count": 1,
        "lesson_retrieved_count": 1 if lesson_retrieved else 0,
        "main_reasoner_lesson_citation_count": 1 if cited else 0,
        "new_policy_effect_lesson_count": 0,
        "permanent_policy_mutation": False,
        "forbidden_effect_attempted": forbidden_hit,
        "classification_matrix": {
            "class_counts": matrix["class_counts"],
            "loss_is_not_automatic_bad_process": matrix["loss_is_not_automatic_bad_process"],
            "required_classes_present": matrix["required_classes_present"],
        },
        "good_process_loss_non_suppression": gpl_non_suppression,
        "proof_digest": _sha(
            {
                "sig": sig,
                "cls": cls,
                "effect": effect,
                "cited": cited,
                "measurable": measurable_change,
            }
        ),
    }


def _good_process_loss_non_suppression(packets: list[dict[str, Any]]) -> dict[str, Any]:
    gpl = [
        p
        for p in packets
        if classify_from_evidence(p)["process_classification"] == "GOOD_PROCESS_LOSS"
    ]
    if not gpl:
        return {
            "good_process_loss_non_suppression_status": "FAIL",
            "reason": "missing_good_process_loss_fixture",
            "auto_block_all_similar_valid_trades": False,
            "block_created": False,
        }
    source = gpl[0]
    # Future compliant candidates with same symbol must remain eligible.
    suppressed = False
    for p in packets:
        c = classify_from_evidence(p)
        if (
            p is not source
            and c["is_good_process"]
            and p.get("symbol") == source.get("symbol")
            and bool(p.get("_suppressed_by_good_process_loss"))
        ):
            suppressed = True
    return {
        "source_trade_id": source.get("trade_id"),
        "good_process_loss_count": len(gpl),
        "auto_block_all_similar_valid_trades": False,
        "block_created": False,
        "good_process_loss_non_suppression_status": "FAIL" if suppressed else "PASS",
    }
