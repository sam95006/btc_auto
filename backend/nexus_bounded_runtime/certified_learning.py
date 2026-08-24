"""Certified durable learning closure after bounded Demo trade."""
from __future__ import annotations

from typing import Any

from backend.nexus_demo_execution.p2_durable_learning_store import DurableLessonStore
from backend.nexus_demo_execution.p2_run8_durable_loader import source_evidence_hash
from backend.nexus_demo_execution.p2_run8_learning_closure import (
    build_lesson_candidate,
    classify_mistakes,
    reflect_run8,
    research_counterfactuals,
)


def trade_outcome_to_case(*, active: dict[str, Any], pnl: dict[str, Any]) -> dict[str, Any]:
    candidate = active.get("candidate") or {}
    symbol = active.get("symbol") or candidate.get("symbol")
    side = active.get("side") or candidate.get("direction")
    trade_id = active.get("trade_id") or active.get("trade_case_id") or "UNKNOWN"
    decision_id = active.get("decision_id") or f"dec_{trade_id}"
    realized = pnl.get("net_pnl") if pnl.get("net_pnl") is not None else pnl.get("realized_demo_pnl")
    entry_price = active.get("entry_price") or pnl.get("entry_price") or active.get("actual_entry_price")
    exit_price = active.get("exit_price") or pnl.get("exit_price") or entry_price
    qty = active.get("qty") or pnl.get("filled_qty") or "0.001"
    open_fee = pnl.get("entry_fee") or pnl.get("open_fee") or "0"
    close_fee = pnl.get("exit_fee") or pnl.get("close_fee") or "0"
    case = {
        "source": "DURABLE_POSTGRES_LEDGER",
        "campaign_id": "bybit-demo-bounded-6h",
        "trade_id": str(trade_id),
        "decision_id": str(decision_id),
        "symbol": str(symbol),
        "side": str(side),
        "realized_demo_pnl": str(realized if realized is not None else "UNKNOWN"),
        "pnl_provenance": pnl.get("pnl_provenance") or "BYBIT_V5_POSITION_CLOSED_PNL",
        "entry_order_id": active.get("entry_order_id") or active.get("bybit_order_id") or "",
        "close_order_id": active.get("close_order_id") or "",
        "actual_entry_price": str(entry_price or "0"),
        "actual_exit_price": str(exit_price or entry_price or "0"),
        "filled_qty": str(qty),
        "open_fee": str(open_fee),
        "close_fee": str(close_fee),
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
        "accounting_json": {
            "entry_fee": open_fee,
            "close_fee": close_fee,
            "gross_pnl": pnl.get("gross_pnl"),
        },
    }
    case["source_evidence_hash"] = source_evidence_hash(case)
    case["run8_evidence_identity"] = case["source_evidence_hash"]
    return case


def write_durable_lesson_from_trade(
    *,
    store: DurableLessonStore,
    active: dict[str, Any],
    pnl: dict[str, Any],
) -> dict[str, Any]:
    case = trade_outcome_to_case(active=active, pnl=pnl)
    if case.get("realized_demo_pnl") in (None, "", "UNKNOWN"):
        return {"ok": False, "reason": "exchange_pnl_missing"}
    reflection = reflect_run8(case)
    mistakes = classify_mistakes(case, reflection)
    counterfactuals = research_counterfactuals(case, reflection)
    lesson = build_lesson_candidate(case, reflection, mistakes, counterfactuals)
    lesson["lesson_id"] = f"LC_{case['source_evidence_hash'][:24]}"
    lesson["source_trade_id"] = case["trade_id"]
    lesson["source_decision_id"] = case["decision_id"]
    lesson["source_evidence_hash"] = case["source_evidence_hash"]
    lesson["policy_truth"] = False
    lesson["revalidation_required"] = True
    stored = store.upsert_lesson(lesson)
    readback = store.get_by_evidence_hash(case["source_evidence_hash"]) or {}
    ok = bool(
        readback.get("lesson_id") == lesson["lesson_id"]
        and readback.get("source_evidence_hash") == case["source_evidence_hash"]
        and readback.get("policy_truth") in (False, 0)
        and readback.get("revalidation_required") in (True, 1)
    )
    return {
        "ok": ok,
        "lesson_id": stored.get("lesson_id"),
        "source_evidence_hash": case["source_evidence_hash"],
        "readback": readback,
    }
