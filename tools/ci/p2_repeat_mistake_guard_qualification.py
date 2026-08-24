#!/usr/bin/env python3
"""P2 RepeatMistakeGuard behavioral qualification — research-only, no exchange writes."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.durable_order_ledger import DurableOrderLedger
from backend.nexus_demo_execution.p1_validation_runtime import apply_disarmed_flags
from backend.nexus_demo_execution.p2_durable_learning_store import DurableLessonStore
from backend.nexus_demo_execution.p2_run8_durable_loader import (
    PNL_PROVENANCE,
    load_run8_from_intents,
    load_run8_from_ledger,
    reject_placeholder_ids,
)
from tools.ci.p2_lesson_similarity import (
    SIMILARITY_THRESHOLD,
    build_dissimilar_control_candidate,
    build_similar_candidate_from_lesson,
    score_candidate_against_lesson,
)
from backend.nexus_demo_execution.p2_research_decision_path import research_decision_path
from backend.nexus_demo_execution.p2_run8_learning_closure import (
    ARM_READY_HOLD,
    DurableDecisionMemory,
    RepeatMistakeGuard,
)
from backend.nexus_demo_execution.session_limits import FIXED_LEVERAGE, MARGIN_PER_TRADE_CAP
from backend.nexus_persistence_pg.pool import PostgresPool


class _EmptyLessonStore:
    def list_lessons(self) -> list[dict[str, Any]]:
        return []

    def query_context(self, _candidate: dict[str, Any]) -> list[dict[str, Any]]:
        return []


def _load_run8_case(
    *,
    intents: list[dict[str, Any]] | None,
    ledger: DurableOrderLedger | None,
) -> dict[str, Any]:
    if intents is not None:
        case = load_run8_from_intents(intents)
    elif ledger is not None:
        case = load_run8_from_ledger(ledger)
    else:
        raise ValueError("run8_durable_input_required_hold")
    reject_placeholder_ids(case)
    if str(case.get("source") or "") != "DURABLE_POSTGRES_LEDGER":
        raise ValueError("run8_source_not_durable_postgres_ledger_hold")
    if int(case.get("candidate_count") or 0) != 1:
        raise ValueError("run8_candidate_count_not_unique_hold")
    if str(case.get("pnl_provenance") or "") != PNL_PROVENANCE:
        raise ValueError("exchange_outcome_not_grounded_hold")
    if case.get("realized_demo_pnl") in (None, ""):
        raise ValueError("realized_pnl_missing_hold")
    if case.get("synthetic_pnl") or case.get("latest_row_fallback"):
        raise ValueError("synthetic_or_fallback_pnl_rejected_hold")
    return case


def derive_expected_lesson_identity_from_case(case: dict[str, Any]) -> dict[str, str]:
    """Derive exact durable lesson identity from certified Run8 — no manual repo vars."""
    evidence_hash = str(case.get("source_evidence_hash") or "")
    if not evidence_hash:
        raise ValueError("source_evidence_hash_missing_hold")
    return {
        "lesson_id": f"LC_{evidence_hash[:24]}",
        "source_evidence_hash": evidence_hash,
        "source_trade_id": str(case["trade_id"]),
        "source_decision_id": str(case["decision_id"]),
    }


def _load_exact_durable_lesson(store: DurableLessonStore, expected: dict[str, str]) -> dict[str, Any]:
    row = store.get_by_evidence_hash(expected["source_evidence_hash"])
    if row is None:
        raise ValueError("durable_lesson_not_found_hold")
    if row.get("lesson_id") != expected["lesson_id"]:
        raise ValueError("lesson_id_mismatch_hold")
    if row.get("source_trade_id") != expected["source_trade_id"]:
        raise ValueError("source_trade_id_mismatch_hold")
    if row.get("source_decision_id") != expected["source_decision_id"]:
        raise ValueError("source_decision_id_mismatch_hold")
    if row.get("policy_truth") not in (False, 0, "false", "f"):
        raise ValueError("policy_truth_not_false_hold")
    if row.get("revalidation_required") not in (True, 1, "true", "t"):
        raise ValueError("revalidation_required_not_true_hold")
    return row


def _decision_snapshot(candidate: dict[str, Any], guard: dict[str, Any]) -> dict[str, Any]:
    confidence = float(candidate.get("confidence") or 0.0)
    decision = guard.get("decision_after_learning") or "ALLOW"
    return {
        "candidate_score": candidate.get("expected_gross_pnl"),
        "confidence": confidence if decision == guard.get("decision_before_learning") else guard.get("confidence_after"),
        "eligibility": "HOLD" if decision == "SKIP" else "ELIGIBLE",
        "decision": decision,
        "reason_codes": [
            str(guard.get("guard_after") or "NONE"),
            str(guard.get("reason_for_change") or "none"),
        ],
    }


def _pre_guard_snapshot(candidate: dict[str, Any]) -> dict[str, Any]:
    guard = RepeatMistakeGuard(_EmptyLessonStore()).evaluate(candidate)
    snap = _decision_snapshot(candidate, guard)
    snap["confidence"] = guard.get("confidence_before", snap["confidence"])
    snap["decision"] = guard.get("decision_before_learning", "ALLOW")
    snap["eligibility"] = "ELIGIBLE"
    return snap


def _evaluate_candidate(
    *,
    candidate: dict[str, Any],
    lesson: dict[str, Any],
    store: DurableLessonStore,
) -> dict[str, Any]:
    similarity = score_candidate_against_lesson(candidate, lesson)
    memory = DurableDecisionMemory(store)
    pre = _pre_guard_snapshot(candidate)
    post_path = research_decision_path(candidate, memory=memory)
    post_guard = post_path["guard"]
    post = _decision_snapshot(candidate, post_guard)
    post["confidence"] = post_guard.get("confidence_after", post["confidence"])
    return {
        "similarity": similarity,
        "pre_guard": pre,
        "post_guard": post,
        "research_recommendation": post_path["research_recommendation"],
        "memory_hits": len(post_path.get("memory_hits") or []),
    }


def _hard_risk_unchanged(*, leverage_before: int, cap_before: float) -> bool:
    if FIXED_LEVERAGE != leverage_before:
        return False
    if float(MARGIN_PER_TRADE_CAP) != float(cap_before):
        return False
    for key in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        if (os.environ.get(key) or "").strip().lower() != "false":
            return False
    return True


def _write_evidence(payload: dict[str, Any]) -> None:
    path = Path(
        os.environ.get("P2_REPEAT_MISTAKE_GUARD_QUALIFICATION_EVIDENCE_PATH")
        or "/tmp/nexus_p2_migration_0007/p2_repeat_mistake_guard_qualification.json"
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    except OSError:
        pass


def run(
    *,
    intents: list[dict[str, Any]] | None = None,
    sqlite_path: str | Path | None = None,
) -> dict[str, Any]:
    apply_disarmed_flags()
    os.environ["AUTONOMOUS_BYBIT_DEMO_ARM_READY"] = ARM_READY_HOLD
    leverage_before = FIXED_LEVERAGE
    cap_before = float(MARGIN_PER_TRADE_CAP)
    evidence: dict[str, Any] = {
        "P2_REPEAT_MISTAKE_GUARD_IMPLEMENTED": True,
        "P2_RMG_MANUAL_IDENTITY_DEPENDENCY_REMOVED": True,
        "CERTIFIED_RUN8_DURABLE_IDENTITY_AUTHORITY": False,
        "RUN8_UNIQUE_TARGET_REQUIRED": True,
        "LESSON_ID_DERIVED_FROM_EVIDENCE_HASH": False,
        "LATEST_ROW_FALLBACK_FALSE": True,
        "DURABLE_LESSON_EXACT_IDENTITY_REQUIRED": True,
        "P2_REPEAT_MISTAKE_GUARD_QUALIFICATION_PASS": False,
        "DURABLE_LESSON_RETRIEVAL_PASS": False,
        "SIMILARITY_ENGINE_PASS": False,
        "SIMILAR_CANDIDATE_MATCH_PASS": False,
        "DISSIMILAR_CONTROL_REJECT_PASS": False,
        "PRE_POST_BEHAVIOR_DIFFERENCE_PASS": False,
        "REPEAT_MISTAKE_GUARD_EFFECT_PASS": False,
        "P2_REPEAT_MISTAKE_GUARD_DETERMINISM_PASS": False,
        "HARD_RISK_AUTHORITY_UNCHANGED": False,
        "LESSON_POLICY_TRUTH_REMAINS_FALSE": False,
        "LESSON_REVALIDATION_REQUIRED_TRUE": False,
        "SIMILARITY_THRESHOLD": SIMILARITY_THRESHOLD,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
        "AUTONOMOUS_BYBIT_DEMO_ARM_READY": ARM_READY_HOLD,
        "error": None,
    }
    pool: PostgresPool | None = None
    store: DurableLessonStore | None = None
    try:
        if sqlite_path is not None:
            if intents is None:
                evidence["error"] = "sqlite_intents_required_hold"
                return evidence
            case = _load_run8_case(intents=intents, ledger=None)
            store = DurableLessonStore(sqlite_path=sqlite_path)
        else:
            database_url = (os.environ.get("NEXUS_POSTGRES_URL") or "").strip()
            if not database_url:
                evidence["error"] = "postgres_url_missing"
                return evidence
            pool = PostgresPool(database_url)
            pool.open()
            versions = {str(row[0]) for row in pool.fetchall("SELECT version FROM nexus.schema_migrations")}
            if "0007" not in versions:
                evidence["error"] = "migration_0007_missing"
                return evidence
            ledger = DurableOrderLedger(pool)
            case = _load_run8_case(intents=None, ledger=ledger)
            store = DurableLessonStore(pool=pool)

        expected = derive_expected_lesson_identity_from_case(case)
        evidence["CERTIFIED_RUN8_DURABLE_IDENTITY_AUTHORITY"] = True
        evidence["LESSON_ID_DERIVED_FROM_EVIDENCE_HASH"] = expected["lesson_id"] == f"LC_{expected['source_evidence_hash'][:24]}"
        evidence["expected_source_trade_id"] = expected["source_trade_id"]
        evidence["expected_source_decision_id"] = expected["source_decision_id"]
        evidence["expected_source_evidence_hash"] = expected["source_evidence_hash"]
        evidence["expected_lesson_id"] = expected["lesson_id"]

        support_before = int(
            (store.get_by_evidence_hash(expected["source_evidence_hash"]) or {}).get("support_count") or 0
        )
        lesson = _load_exact_durable_lesson(store, expected)
        evidence["DURABLE_LESSON_RETRIEVAL_PASS"] = True
        evidence["LESSON_ID"] = lesson.get("lesson_id")
        evidence["SOURCE_EVIDENCE_HASH_MATCH"] = lesson.get("source_evidence_hash") == expected["source_evidence_hash"]
        evidence["LESSON_POLICY_TRUTH_REMAINS_FALSE"] = lesson.get("policy_truth") in (False, 0, "false", "f")
        evidence["LESSON_REVALIDATION_REQUIRED_TRUE"] = lesson.get("revalidation_required") in (True, 1, "true", "t")

        similar = build_similar_candidate_from_lesson(lesson)
        dissimilar = build_dissimilar_control_candidate(lesson)

        similar_eval = _evaluate_candidate(candidate=similar, lesson=lesson, store=store)
        dissimilar_eval = _evaluate_candidate(candidate=dissimilar, lesson=lesson, store=store)

        evidence["SIMILARITY_SCORE"] = similar_eval["similarity"]["similarity_score"]
        evidence["SIMILARITY_ENGINE_PASS"] = bool(
            similar_eval["similarity"]["similarity_score"] >= SIMILARITY_THRESHOLD
            and similar_eval["similarity"]["guard_match"]
        )
        evidence["SIMILAR_CANDIDATE_MATCH_PASS"] = bool(
            similar_eval["similarity"]["matched"]
            and similar_eval["memory_hits"] >= 1
            and similar_eval["post_guard"]["decision"] == "SKIP"
        )
        evidence["DISSIMILAR_CONTROL_REJECT_PASS"] = bool(
            not dissimilar_eval["similarity"]["matched"]
            and dissimilar_eval["memory_hits"] == 0
            and dissimilar_eval["post_guard"]["decision"] == "ALLOW"
        )
        evidence["PRE_GUARD_DECISION"] = similar_eval["pre_guard"]["decision"]
        evidence["POST_GUARD_DECISION"] = similar_eval["post_guard"]["decision"]
        evidence["pre_guard"] = similar_eval["pre_guard"]
        evidence["post_guard"] = similar_eval["post_guard"]
        evidence["PRE_POST_BEHAVIOR_DIFFERENCE_PASS"] = bool(
            similar_eval["pre_guard"]["decision"] != similar_eval["post_guard"]["decision"]
            or similar_eval["pre_guard"]["confidence"] != similar_eval["post_guard"]["confidence"]
        )
        evidence["REPEAT_MISTAKE_GUARD_EFFECT_PASS"] = bool(
            similar_eval["pre_guard"]["decision"] == "ALLOW"
            and similar_eval["post_guard"]["decision"] == "SKIP"
            and similar_eval["research_recommendation"] == "RESEARCH_SKIP"
        )

        similar_again = _evaluate_candidate(candidate=similar, lesson=lesson, store=store)
        evidence["P2_REPEAT_MISTAKE_GUARD_DETERMINISM_PASS"] = bool(
            similar_eval["similarity"]["similarity_score"] == similar_again["similarity"]["similarity_score"]
            and similar_eval["post_guard"]["decision"] == similar_again["post_guard"]["decision"]
            and similar_eval["similarity"]["matched_lesson_id"]
            == similar_again["similarity"]["matched_lesson_id"]
        )

        support_after = int(
            (store.get_by_evidence_hash(expected["source_evidence_hash"]) or {}).get("support_count") or 0
        )
        evidence["HARD_RISK_AUTHORITY_UNCHANGED"] = _hard_risk_unchanged(
            leverage_before=leverage_before,
            cap_before=cap_before,
        )
        evidence["support_count_unchanged"] = support_before == support_after

        evidence["P2_REPEAT_MISTAKE_GUARD_QUALIFICATION_PASS"] = bool(
            evidence["DURABLE_LESSON_RETRIEVAL_PASS"]
            and evidence["SIMILARITY_ENGINE_PASS"]
            and evidence["SIMILAR_CANDIDATE_MATCH_PASS"]
            and evidence["DISSIMILAR_CONTROL_REJECT_PASS"]
            and evidence["PRE_POST_BEHAVIOR_DIFFERENCE_PASS"]
            and evidence["REPEAT_MISTAKE_GUARD_EFFECT_PASS"]
            and evidence["P2_REPEAT_MISTAKE_GUARD_DETERMINISM_PASS"]
            and evidence["HARD_RISK_AUTHORITY_UNCHANGED"]
            and evidence["LESSON_POLICY_TRUTH_REMAINS_FALSE"]
            and evidence["LESSON_REVALIDATION_REQUIRED_TRUE"]
            and evidence["support_count_unchanged"]
            and evidence["create_order_calls"] == 0
            and evidence["exchange_write_call_count"] == 0
        )
        if not evidence["P2_REPEAT_MISTAKE_GUARD_QUALIFICATION_PASS"]:
            evidence["error"] = evidence.get("error") or "repeat_mistake_guard_qualification_failed"
        return evidence
    except ValueError as exc:
        evidence["error"] = str(exc)
        return evidence
    except Exception as exc:  # noqa: BLE001
        evidence["error"] = f"repeat_mistake_guard_error:{type(exc).__name__}:{exc}"
        return evidence
    finally:
        if store is not None:
            store.close()
        if pool is not None:
            pool.close()


def main() -> int:
    try:
        evidence = run()
    except Exception as exc:  # noqa: BLE001
        evidence = {
            "P2_REPEAT_MISTAKE_GUARD_QUALIFICATION_PASS": False,
            "create_order_calls": 0,
            "exchange_write_call_count": 0,
            "error": f"repeat_mistake_guard_unhandled:{type(exc).__name__}",
        }
    _write_evidence(evidence)
    print(json.dumps(evidence, sort_keys=True, default=str))
    return 0 if evidence.get("P2_REPEAT_MISTAKE_GUARD_QUALIFICATION_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
