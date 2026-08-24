"""Certified durable learning closure after bounded Demo trade — no synthetic evidence."""
from __future__ import annotations

from typing import Any

from backend.nexus_demo_execution.p2_durable_learning_store import DurableLessonStore
from backend.nexus_demo_execution.p2_run8_durable_loader import PNL_PROVENANCE, source_evidence_hash
from backend.nexus_demo_execution.p2_run8_learning_closure import (
    build_lesson_candidate,
    classify_mistakes,
    reflect_run8,
    research_counterfactuals,
)


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text or text.upper() == "UNKNOWN":
        raise ValueError(f"{field}_missing")
    return text


def find_closed_pnl_by_order_id(writer: Any, *, symbol: str, close_order_id: str) -> dict[str, Any] | None:
    list_fn = getattr(writer, "list_closed_pnl", None)
    if not callable(list_fn):
        return None
    for row in list_fn(symbol=symbol, limit=50):
        if not isinstance(row, dict):
            continue
        if str(row.get("orderId") or "") == str(close_order_id):
            return row
    return None


def validate_exchange_outcome_evidence(
    *,
    writer: Any,
    active: dict[str, Any],
    pnl: dict[str, Any],
) -> dict[str, Any]:
    try:
        symbol = _required_text(active.get("symbol"), "symbol")
        close_order_id = _required_text(active.get("close_order_id"), "close_order_id")
        entry_order_id = _required_text(active.get("entry_order_id") or active.get("bybit_order_id"), "entry_order_id")
    except ValueError as exc:
        return {"ok": False, "reason": "LEARNING_CLOSURE_HOLD", "detail": str(exc)}

    closed_row = find_closed_pnl_by_order_id(writer, symbol=symbol, close_order_id=close_order_id)
    if closed_row is None:
        return {"ok": False, "reason": "LEARNING_CLOSURE_HOLD", "detail": "closed_pnl_order_id_not_found"}

    if str(closed_row.get("orderId") or "") != close_order_id:
        return {"ok": False, "reason": "LEARNING_CLOSURE_HOLD", "detail": "closed_pnl_order_id_mismatch"}

    provenance = str(pnl.get("pnl_provenance") or "").strip()
    if not provenance:
        return {"ok": False, "reason": "LEARNING_CLOSURE_HOLD", "detail": "pnl_provenance_missing"}
    if provenance != PNL_PROVENANCE:
        return {"ok": False, "reason": "LEARNING_CLOSURE_HOLD", "detail": "exchange_pnl_provenance_invalid"}

    realized = pnl.get("net_pnl")
    if realized is None and pnl.get("realized_demo_pnl") is not None:
        realized = pnl.get("realized_demo_pnl")
    if realized is None or str(realized).strip() == "":
        return {"ok": False, "reason": "LEARNING_CLOSURE_HOLD", "detail": "exchange_realized_pnl_missing"}

    try:
        entry_price = _required_text(
            active.get("actual_entry_price") or closed_row.get("avgEntryPrice") or pnl.get("entry_price"),
            "actual_entry_price",
        )
        exit_price = _required_text(
            active.get("actual_exit_price") or closed_row.get("avgExitPrice") or pnl.get("exit_price"),
            "actual_exit_price",
        )
        filled_qty = _required_text(active.get("qty") or closed_row.get("qty") or pnl.get("filled_qty"), "filled_qty")
        trade_id = _required_text(active.get("trade_id"), "trade_id")
        decision_id = _required_text(active.get("decision_id"), "decision_id")
        side = _required_text(active.get("side"), "side")
    except ValueError as exc:
        return {"ok": False, "reason": "LEARNING_CLOSURE_HOLD", "detail": str(exc)}

    open_fee = pnl.get("entry_fee") if pnl.get("entry_fee") is not None else pnl.get("open_fee")
    close_fee = pnl.get("exit_fee") if pnl.get("exit_fee") is not None else pnl.get("close_fee")
    if open_fee is None or close_fee is None:
        return {"ok": False, "reason": "LEARNING_CLOSURE_HOLD", "detail": "exchange_fee_fields_missing"}

    case = {
        "source": "DURABLE_POSTGRES_LEDGER",
        "campaign_id": "bybit-demo-bounded-6h",
        "trade_id": trade_id,
        "decision_id": decision_id,
        "symbol": symbol,
        "side": side,
        "realized_demo_pnl": str(realized),
        "pnl_provenance": provenance,
        "entry_order_id": entry_order_id,
        "close_order_id": close_order_id,
        "actual_entry_price": entry_price,
        "actual_exit_price": exit_price,
        "filled_qty": filled_qty,
        "open_fee": str(open_fee),
        "close_fee": str(close_fee),
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
        "accounting_json": {
            "entry_fee": open_fee,
            "close_fee": close_fee,
            "gross_pnl": pnl.get("gross_pnl"),
            "closed_pnl_order_id": close_order_id,
        },
    }
    case["source_evidence_hash"] = source_evidence_hash(case)
    case["run8_evidence_identity"] = case["source_evidence_hash"]
    return {"ok": True, "case": case, "closed_pnl_row": closed_row}


def write_durable_lesson_from_trade(
    *,
    store: DurableLessonStore,
    writer: Any,
    active: dict[str, Any],
    pnl: dict[str, Any],
) -> dict[str, Any]:
    validated = validate_exchange_outcome_evidence(writer=writer, active=active, pnl=pnl)
    if not validated.get("ok"):
        return validated
    case = validated["case"]
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
    if not ok:
        return {"ok": False, "reason": "LEARNING_CLOSURE_HOLD", "detail": "durable_lesson_readback_failed"}
    return {
        "ok": True,
        "lesson_id": stored.get("lesson_id"),
        "source_evidence_hash": case["source_evidence_hash"],
        "readback": readback,
    }
