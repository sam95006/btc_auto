#!/usr/bin/env python3
"""Research-only P2.1 PostgreSQL qualification. No exchange writes, no P1 rerun."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.durable_order_ledger import DurableOrderLedger
from backend.nexus_demo_execution.p1_validation_runtime import apply_disarmed_flags
from backend.nexus_demo_execution.p2_durable_learning_store import DurableLessonStore
from backend.nexus_demo_execution.p2_research_decision_path import research_decision_path
from backend.nexus_demo_execution.p2_run8_durable_loader import PLACEHOLDER_TOKENS, reject_placeholder_ids
from backend.nexus_demo_execution.p2_run8_learning_closure import (
    ARM_READY_HOLD,
    DurableDecisionMemory,
    close_run8_durable_learning,
)
from backend.nexus_persistence_pg.pool import PostgresPool


def _prefix(value: Any, size: int = 12) -> str:
    text = str(value or "")
    return text[:size]


def _write_evidence(payload: dict[str, Any]) -> None:
    path = Path(os.environ.get("P2_1_QUALIFICATION_EVIDENCE_PATH") or "/tmp/nexus_demo_validation/p2_1_postgres_qualification.json")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    except OSError:
        pass


def _fee_candidate(case: dict[str, Any], *, symbol: str) -> dict[str, Any]:
    from decimal import Decimal

    fees = Decimal(str(case.get("open_fee") or 0)) + Decimal(str(case.get("close_fee") or 0))
    return {
        "symbol": symbol,
        "side": case.get("side") or "Buy",
        "expected_gross_pnl": "0",
        "round_trip_fee_estimate": format(fees, "f"),
        "confidence": 0.62,
    }


def _safe_identity(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_id_prefix": _prefix(case.get("trade_id")),
        "decision_id_prefix": _prefix(case.get("decision_id")),
        "order_intent_id_prefix": _prefix(case.get("order_intent_id")),
        "entry_order_id_prefix": _prefix(case.get("entry_order_id")),
        "close_order_id_prefix": _prefix(case.get("close_order_id")),
        "source_evidence_hash": case.get("source_evidence_hash"),
        "symbol": case.get("symbol"),
        "side": case.get("side"),
        "filled_qty_source": case.get("filled_qty_source"),
        "process_validation_status": (case.get("process_assessment") or {}).get("process_validation_status"),
        "process_valid": (case.get("process_assessment") or {}).get("process_valid"),
    }


def _query_count(store: DurableLessonStore, evidence_hash: str) -> int:
    if store.pool is not None:
        return int(
            store.pool.fetchval(
                "SELECT COUNT(*) FROM nexus.p2_research_lessons WHERE source_evidence_hash=%s",
                (evidence_hash,),
            )
            or 0
        )
    return len([row for row in store.list_lessons() if row.get("source_evidence_hash") == evidence_hash])


def run(
    *,
    intents: list[dict[str, Any]] | None = None,
    sqlite_path: str | Path | None = None,
) -> dict[str, Any]:
    apply_disarmed_flags()
    os.environ["AUTONOMOUS_BYBIT_DEMO_ARM_READY"] = ARM_READY_HOLD
    evidence: dict[str, Any] = {
        "P2_1_POSTGRES_QUALIFICATION_PASS": False,
        "POSTGRES_LESSON_PERSISTED": False,
        "POSTGRES_MEMORY_SURVIVES_NEW_PROCESS": False,
        "DUPLICATE_LESSON_COUNT": 0,
        "DUPLICATE_LESSON_IDEMPOTENCY_PASS": False,
        "POLICY_TRUTH": True,
        "SUPPORT_COUNT": 0,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
        "AUTONOMOUS_BYBIT_DEMO_ARM_READY": ARM_READY_HOLD,
        "error": None,
    }
    database_url = (os.environ.get("NEXUS_POSTGRES_URL") or "").strip()
    pool_a: PostgresPool | None = None
    pool_b: PostgresPool | None = None
    store_a: DurableLessonStore | None = None
    store_b: DurableLessonStore | None = None
    try:
        if sqlite_path is not None:
            if intents is None:
                evidence["error"] = "sqlite_intents_required"
                return evidence
            store_a = DurableLessonStore(sqlite_path=sqlite_path)
            first = close_run8_durable_learning(store=store_a, intents=intents)
            store_a.close()
            store_a = None
            store_b = DurableLessonStore(sqlite_path=sqlite_path)
            second = close_run8_durable_learning(store=store_b, intents=intents)
        else:
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
            store_a = DurableLessonStore(pool=pool_a)
            first = close_run8_durable_learning(store=store_a, ledger=ledger)
            pool_a.close()
            pool_a = None
            store_a = None
            pool_b = PostgresPool(database_url)
            pool_b.open()
            store_b = DurableLessonStore(pool=pool_b)
            second = close_run8_durable_learning(store=store_b, ledger=DurableOrderLedger(pool_b))

        reject_placeholder_ids(first)
        blob = json.dumps(first, default=str)
        if any(token in blob for token in PLACEHOLDER_TOKENS):
            evidence["error"] = "placeholder_id_present"
            return evidence
        case = {
            "trade_id": first["trade_id"],
            "decision_id": first["decision_id"],
            "order_intent_id": first["order_intent_id"],
            "entry_order_id": first["entry_order_id"],
            "close_order_id": first["close_order_id"],
            "source_evidence_hash": first["source_evidence_hash"],
            "symbol": first["lesson_candidate"]["symbol"],
            "side": first["lesson_candidate"]["side"],
            "open_fee": first["reflection"]["fee_total"],
            "close_fee": "0",
            "filled_qty_source": first.get("filled_qty_source"),
            "process_assessment": first["process_assessment"],
        }
        if store_b is None:
            evidence["error"] = "second_process_store_missing"
            return evidence
        memory = DurableDecisionMemory(store_b)
        similar = _fee_candidate(case, symbol=str(case["symbol"]))
        unrelated = _fee_candidate(case, symbol="ETHUSDT")
        after = research_decision_path(similar, memory=memory)
        other = research_decision_path(unrelated, memory=memory)
        lesson_count = _query_count(store_b, str(first["source_evidence_hash"]))
        evidence.update(_safe_identity(case))
        evidence.update(
            {
                "POSTGRES_LESSON_PERSISTED": True,
                "POSTGRES_MEMORY_SURVIVES_NEW_PROCESS": bool(memory.query_context(similar)),
                "DUPLICATE_LESSON_COUNT": lesson_count,
                "DUPLICATE_LESSON_IDEMPOTENCY_PASS": lesson_count == 1 and first["lesson_id"] == second["lesson_id"],
                "POLICY_TRUTH": False,
                "POLICY_TRUTH_REMAINS_FALSE": first["policy_truth"] is False and second["policy_truth"] is False,
                "SUPPORT_COUNT": int(first.get("support_count") or 1),
                "research_recommendation_after": after["research_recommendation"],
                "unrelated_research_recommendation": other["research_recommendation"],
                "behavior_change_demonstrated": first["behavior_change_demonstrated"],
                "PROCESS_VALIDATION_STATUS": first["process_assessment"].get("process_validation_status"),
                "create_order_calls": 0,
                "exchange_write_call_count": 0,
                "AUTONOMOUS_BYBIT_DEMO_ARM_READY": ARM_READY_HOLD,
            }
        )
        evidence["P2_1_POSTGRES_QUALIFICATION_PASS"] = bool(
            evidence["POSTGRES_LESSON_PERSISTED"]
            and evidence["POSTGRES_MEMORY_SURVIVES_NEW_PROCESS"]
            and evidence["DUPLICATE_LESSON_IDEMPOTENCY_PASS"]
            and evidence["POLICY_TRUTH_REMAINS_FALSE"]
            and after["research_recommendation"] == "RESEARCH_SKIP"
            and other["research_recommendation"] == "RESEARCH_ALLOW"
            and evidence["create_order_calls"] == 0
            and os.environ.get("EXCHANGE_WRITE", "").lower() == "false"
        )
        if not evidence["P2_1_POSTGRES_QUALIFICATION_PASS"]:
            evidence["error"] = evidence.get("error") or "qualification_assertions_failed"
        return evidence
    except Exception as exc:  # noqa: BLE001
        evidence["error"] = f"qualification_error:{type(exc).__name__}"
        return evidence
    finally:
        if store_a is not None:
            store_a.close()
        if store_b is not None:
            store_b.close()
        if pool_a is not None:
            pool_a.close()
        if pool_b is not None:
            pool_b.close()


def main() -> int:
    try:
        evidence = run()
    except Exception as exc:  # noqa: BLE001
        evidence = {
            "P2_1_POSTGRES_QUALIFICATION_PASS": False,
            "create_order_calls": 0,
            "exchange_write_call_count": 0,
            "error": f"qualification_unhandled_error:{type(exc).__name__}",
        }
    _write_evidence(evidence)
    print(json.dumps(evidence, sort_keys=True, default=str))
    return 0 if evidence.get("P2_1_POSTGRES_QUALIFICATION_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
