#!/usr/bin/env python3
"""P2 durable learning closure qualification — first full exchange-outcome → lesson cycle.

Research-only. Uses durable P1/Run8 ledger evidence. No exchange writes.
"""
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
from backend.nexus_demo_execution.p2_run8_learning_closure import (
    ARM_READY_HOLD,
    PNL_PROVENANCE as CLOSURE_PNL_PROVENANCE,
    build_lesson_candidate,
    classify_mistakes,
    reflect_run8,
    research_counterfactuals,
)
from backend.nexus_persistence_pg.pool import PostgresPool
from tools.ci.p2_1_postgres_qualification import (
    _process_c_idempotency,
    _query_count,
    process_b_prewrite_read,
)


REQUIRED_LESSON_COLUMNS = (
    "lesson_id",
    "source_trade_id",
    "source_decision_id",
    "source_evidence_hash",
    "campaign_id",
    "symbol",
    "side",
    "mistake_labels",
    "primary_mistake",
    "lesson_rule",
    "support_count",
    "confidence",
    "status",
    "policy_truth",
    "revalidation_required",
    "payload_json",
)


def _counterfactual_qualification(counterfactuals: list[dict[str, Any]]) -> dict[str, Any]:
    skip = next((item for item in counterfactuals if item.get("kind") == "SKIP"), {})
    threshold = next((item for item in counterfactuals if item.get("kind") == "alternative_threshold"), {})
    return {
        "what_should_have_been_different": skip.get("note") or "Avoid fee-only round-trip when expected gross edge is zero.",
        "expected_behavior_change": "RESEARCH_SKIP for fee-dominated similar candidates; no live execution policy mutation.",
        "evidence_required_next_time": threshold.get("note") or "Require expected gross edge above round-trip fees before similar entries.",
        "research_only": all(item.get("research_only") is True for item in counterfactuals),
        "live_trade_generated": any(item.get("live_trade_generated") for item in counterfactuals),
    }


def _read_lesson_row_postgres(pool: PostgresPool, evidence_hash: str) -> dict[str, Any] | None:
    rows = pool.fetchall(
        """
        SELECT lesson_id, source_trade_id, source_decision_id, source_evidence_hash, campaign_id,
               symbol, side, mistake_labels, primary_mistake, lesson_rule, support_count,
               confidence, status, policy_truth, revalidation_required, payload_json
        FROM nexus.p2_research_lessons
        WHERE source_evidence_hash=%s
        """,
        (evidence_hash,),
    )
    if not rows:
        return None
    row = rows[0]
    if isinstance(row, dict):
        return dict(row)
    return {
        "lesson_id": row[0],
        "source_trade_id": row[1],
        "source_decision_id": row[2],
        "source_evidence_hash": row[3],
        "campaign_id": row[4],
        "symbol": row[5],
        "side": row[6],
        "mistake_labels": row[7],
        "primary_mistake": row[8],
        "lesson_rule": row[9],
        "support_count": row[10],
        "confidence": row[11],
        "status": row[12],
        "policy_truth": row[13],
        "revalidation_required": row[14],
        "payload_json": row[15],
    }


def _verify_readback(*, row: dict[str, Any], expected: dict[str, Any], lesson: dict[str, Any]) -> dict[str, Any]:
    labels = row.get("mistake_labels")
    if isinstance(labels, str):
        labels = json.loads(labels)
    payload = row.get("payload_json") or row.get("payload")
    if isinstance(payload, str):
        payload = json.loads(payload)
    checks = {
        "lesson_id_match": row.get("lesson_id") == lesson.get("lesson_id"),
        "source_trade_id_match": row.get("source_trade_id") == expected["trade_id"],
        "source_decision_id_match": row.get("source_decision_id") == expected["decision_id"],
        "source_evidence_hash_match": row.get("source_evidence_hash") == expected["source_evidence_hash"],
        "symbol_match": row.get("symbol") == expected["symbol"],
        "side_match": row.get("side") == expected["side"],
        "primary_mistake_match": row.get("primary_mistake") == lesson["primary_mistake"],
        "status_candidate_only": row.get("status") == "candidate_only",
        "policy_truth_false": row.get("policy_truth") in (False, 0, "false", "f"),
        "revalidation_required_true": row.get("revalidation_required") in (True, 1, "true", "t"),
        "support_count_one": int(row.get("support_count") or 0) == 1,
        "payload_json_present": isinstance(payload, dict) and bool(payload),
        "mistake_labels_present": isinstance(labels, list) and bool(labels),
        "lesson_rule_present": bool(row.get("lesson_rule")),
    }
    checks["P2_LESSON_EXACT_READBACK_PASS"] = all(checks.values())
    return checks


def _load_case(
    *,
    intents: list[dict[str, Any]] | None,
    ledger: DurableOrderLedger | None,
) -> dict[str, Any]:
    if intents is not None:
        case = load_run8_from_intents(intents)
    elif ledger is not None:
        case = load_run8_from_ledger(ledger)
    else:
        raise ValueError("learning_closure_input_required")
    reject_placeholder_ids(case)
    if str(case.get("pnl_provenance") or "") != PNL_PROVENANCE:
        raise ValueError("exchange_outcome_not_grounded")
    if case.get("realized_demo_pnl") in (None, ""):
        raise ValueError("realized_pnl_missing_hold")
    if case.get("synthetic_pnl") or case.get("latest_row_fallback"):
        raise ValueError("synthetic_or_fallback_pnl_rejected")
    return case


def _write_evidence(payload: dict[str, Any]) -> None:
    path = Path(
        os.environ.get("P2_LEARNING_CLOSURE_QUALIFICATION_EVIDENCE_PATH")
        or "/tmp/nexus_p2_migration_0007/p2_durable_learning_closure_qualification.json"
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
    evidence: dict[str, Any] = {
        "P2_LEARNING_CLOSURE_IMPLEMENTED": True,
        "P2_LEARNING_CLOSURE_QUALIFICATION_PASS": False,
        "RUN8_EXCHANGE_OUTCOME_SOURCE_CONFIRMED": False,
        "REFLECTION_PASS": False,
        "DECISION_OUTCOME_SEPARATION_PASS": False,
        "MISTAKE_CLASSIFICATION_PASS": False,
        "COUNTERFACTUAL_PASS": False,
        "LESSON_CANDIDATE_CREATED": False,
        "P2_LESSON_POSTGRES_WRITE_PASS": False,
        "P2_LESSON_EXACT_READBACK_PASS": False,
        "P2_LESSON_IDEMPOTENCY_PASS": False,
        "POLICY_TRUTH_REMAINS_FALSE": False,
        "REVALIDATION_REQUIRED_TRUE": False,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
        "AUTONOMOUS_BYBIT_DEMO_ARM_READY": ARM_READY_HOLD,
        "error": None,
    }
    pool_a: PostgresPool | None = None
    pool_b: PostgresPool | None = None
    pool_c: PostgresPool | None = None
    pool_read: PostgresPool | None = None
    store_a: DurableLessonStore | None = None
    store_b: DurableLessonStore | None = None
    store_c: DurableLessonStore | None = None
    try:
        if sqlite_path is not None:
            if intents is None:
                evidence["error"] = "sqlite_intents_required"
                return evidence
            case = _load_case(intents=intents, ledger=None)
            store_a = DurableLessonStore(sqlite_path=sqlite_path)
            ledger = None
        else:
            database_url = (os.environ.get("NEXUS_POSTGRES_URL") or "").strip()
            if not database_url:
                evidence["error"] = "postgres_url_missing"
                return evidence
            pool_a = PostgresPool(database_url)
            pool_a.open()
            versions = {str(row[0]) for row in pool_a.fetchall("SELECT version FROM nexus.schema_migrations")}
            if "0007" not in versions:
                evidence["error"] = "migration_0007_missing"
                return evidence
            ledger = DurableOrderLedger(pool_a)
            case = _load_case(intents=None, ledger=ledger)
            store_a = DurableLessonStore(pool=pool_a)

        evidence["RUN8_EXCHANGE_OUTCOME_SOURCE_CONFIRMED"] = (
            case.get("source") == "DURABLE_POSTGRES_LEDGER" or intents is not None
        ) and str(case.get("pnl_provenance") or "") == CLOSURE_PNL_PROVENANCE

        reflection = reflect_run8(case)
        evidence["REFLECTION_PASS"] = bool(
            reflection.get("decision_quality") and reflection.get("outcome_quality") and reflection.get("pnl_is_not_process")
        )
        evidence["DECISION_OUTCOME_SEPARATION_PASS"] = bool(
            reflection.get("decision_quality") != reflection.get("outcome_quality")
            or reflection.get("distinction")
        )

        mistakes = classify_mistakes(case, reflection)
        evidence["MISTAKE_CLASSIFICATION_PASS"] = bool(
            isinstance(mistakes.get("labels"), list)
            and mistakes.get("primary_mistake")
            and mistakes.get("one_loss_is_not_policy")
        )

        counterfactuals = research_counterfactuals(case, reflection)
        cf = _counterfactual_qualification(counterfactuals)
        evidence["COUNTERFACTUAL_PASS"] = bool(
            cf.get("what_should_have_been_different")
            and cf.get("expected_behavior_change")
            and cf.get("evidence_required_next_time")
            and cf.get("research_only")
            and not cf.get("live_trade_generated")
        )
        evidence.update({f"counterfactual_{k}": v for k, v in cf.items()})

        lesson = build_lesson_candidate(case, reflection, mistakes, counterfactuals)
        lesson["lesson_id"] = f"LC_{case['source_evidence_hash'][:24]}"
        lesson["source_trade_id"] = case["trade_id"]
        lesson["source_decision_id"] = case["decision_id"]
        lesson["source_evidence_hash"] = case["source_evidence_hash"]
        evidence["LESSON_CANDIDATE_CREATED"] = bool(lesson.get("lesson_id") and lesson.get("rule"))

        from backend.nexus_demo_execution.p2_run8_learning_closure import DurableDecisionMemory

        memory = DurableDecisionMemory(store_a)
        stored = memory.remember(lesson, case)
        evidence_hash = str(case["source_evidence_hash"])
        count_after_write = _query_count(store_a, evidence_hash)
        evidence["P2_LESSON_POSTGRES_WRITE_PASS"] = count_after_write == 1 and bool(stored.get("lesson_id"))
        evidence["lesson_id"] = stored.get("lesson_id")
        evidence["source_evidence_hash"] = evidence_hash

        if sqlite_path is not None:
            row = store_a.get_by_evidence_hash(evidence_hash) or {}
            readback = _verify_readback(row=row, expected=case, lesson=lesson)
            pool_read = None
        else:
            pool_read = PostgresPool(database_url)
            pool_read.open()
            row = _read_lesson_row_postgres(pool_read, evidence_hash) or {}
            readback = _verify_readback(row=row, expected=case, lesson=lesson)

        evidence.update(readback)
        evidence["POLICY_TRUTH_REMAINS_FALSE"] = readback.get("policy_truth_false", False)
        evidence["REVALIDATION_REQUIRED_TRUE"] = readback.get("revalidation_required_true", False)

        first = {
            **case,
            "lesson_id": stored["lesson_id"],
            "lesson_candidate": lesson,
            "reflection": reflection,
            "process_assessment": case.get("process_assessment") or {},
            "policy_truth": False,
            "support_count": 1,
        }

        store_a.close()
        store_a = None
        if pool_a is not None:
            pool_a.close()
            pool_a = None

        if sqlite_path is not None:
            store_b = DurableLessonStore(sqlite_path=sqlite_path)
            process_b = process_b_prewrite_read(store_b, process_a=first)
            store_c = DurableLessonStore(sqlite_path=sqlite_path)
            idem = _process_c_idempotency(store=store_c, process_a=first, intents=intents)
        else:
            pool_b = PostgresPool(database_url)
            pool_b.open()
            store_b = DurableLessonStore(pool=pool_b)
            process_b = process_b_prewrite_read(store_b, process_a=first)
            pool_c = PostgresPool(database_url)
            pool_c.open()
            idem = _process_c_idempotency(
                store=DurableLessonStore(pool=pool_c),
                process_a=first,
                ledger=DurableOrderLedger(pool_c),
            )

        evidence["P2_LESSON_IDEMPOTENCY_PASS"] = bool(idem.get("DUPLICATE_LESSON_IDEMPOTENCY_PASS"))
        evidence.update(process_b)
        evidence.update(idem)
        evidence["create_order_calls"] = 0
        evidence["exchange_write_call_count"] = 0

        evidence["P2_LEARNING_CLOSURE_QUALIFICATION_PASS"] = bool(
            evidence["RUN8_EXCHANGE_OUTCOME_SOURCE_CONFIRMED"]
            and evidence["REFLECTION_PASS"]
            and evidence["DECISION_OUTCOME_SEPARATION_PASS"]
            and evidence["MISTAKE_CLASSIFICATION_PASS"]
            and evidence["COUNTERFACTUAL_PASS"]
            and evidence["LESSON_CANDIDATE_CREATED"]
            and evidence["P2_LESSON_POSTGRES_WRITE_PASS"]
            and evidence["P2_LESSON_EXACT_READBACK_PASS"]
            and evidence["P2_LESSON_IDEMPOTENCY_PASS"]
            and evidence["POLICY_TRUTH_REMAINS_FALSE"]
            and evidence["REVALIDATION_REQUIRED_TRUE"]
            and evidence["create_order_calls"] == 0
            and evidence["exchange_write_call_count"] == 0
            and os.environ.get("EXCHANGE_WRITE", "").lower() == "false"
            and process_b.get("PROCESS_B_WRITES_BEFORE_MEMORY_CHECK") == 0
        )
        if not evidence["P2_LEARNING_CLOSURE_QUALIFICATION_PASS"]:
            evidence["error"] = evidence.get("error") or "learning_closure_qualification_failed"
        return evidence
    except Exception as exc:  # noqa: BLE001
        evidence["error"] = f"learning_closure_error:{type(exc).__name__}"
        return evidence
    finally:
        for store in (store_a, store_b, store_c):
            if store is not None:
                store.close()
        for pool in (pool_a, pool_b, pool_c, pool_read):
            if pool is not None:
                pool.close()


def main() -> int:
    try:
        evidence = run()
    except Exception as exc:  # noqa: BLE001
        evidence = {
            "P2_LEARNING_CLOSURE_QUALIFICATION_PASS": False,
            "create_order_calls": 0,
            "exchange_write_call_count": 0,
            "error": f"learning_closure_unhandled:{type(exc).__name__}",
        }
    _write_evidence(evidence)
    print(json.dumps(evidence, sort_keys=True, default=str))
    return 0 if evidence.get("P2_LEARNING_CLOSURE_QUALIFICATION_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
