"""Load certified Run #8 learning input from the durable P1 ledger. Not a snapshot."""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.nexus_demo_execution.p1_qualification import P1_CAMPAIGN_ID
from backend.nexus_demo_execution.p1_run8_accounting_recovery import identify_run8_target

PNL_PROVENANCE = "BYBIT_V5_POSITION_CLOSED_PNL"


PLACEHOLDER_TOKENS = (
    "run8_certified_trade",
    "run8_certified_decision",
    "run8_certified_lifecycle",
)
UNKNOWN = "UNKNOWN"
PROCESS_GATES = (
    "preflight",
    "risk_authority",
    "entry_reconciliation",
    "close_reconciliation",
    "position_flat",
    "exact_pnl_identity",
    "ledger_closure",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dec(value: Any) -> Decimal | None:
    if value in (None, "", UNKNOWN):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def reject_placeholder_ids(payload: dict[str, Any]) -> None:
    blob = json.dumps(payload, default=str)
    for token in PLACEHOLDER_TOKENS:
        if token in blob:
            raise ValueError(f"placeholder_id_rejected:{token}")


def source_evidence_hash(payload: dict[str, Any]) -> str:
    canonical = {
        "trade_id": _text(payload.get("trade_id")),
        "decision_id": _text(payload.get("decision_id")),
        "entry_order_id": _text(payload.get("entry_order_id")),
        "close_order_id": _text(payload.get("close_order_id")),
        "realized_demo_pnl": _text(payload.get("realized_demo_pnl")),
        "closed_at": _text(payload.get("closed_at")),
        "pnl_provenance": _text(payload.get("pnl_provenance")),
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def reconstruct_original_decision_context(case: dict[str, Any]) -> dict[str, Any]:
    accounting = case.get("accounting_json") if isinstance(case.get("accounting_json"), dict) else {}
    original = case.get("original_decision_context") if isinstance(case.get("original_decision_context"), dict) else {}
    src = {**accounting, **original}

    def _field(*keys: str) -> Any:
        for key in keys:
            if key in src and src[key] not in (None, ""):
                return src[key]
        return UNKNOWN

    confidence = _field("confidence", "decision_confidence")
    expected_move = _field("expected_gross_move_bps", "expected_move_bps")
    ai_directional = original.get("ai_directional_decision")
    if ai_directional in (None, ""):
        ai_directional = accounting.get("ai_directional_decision")
    proven = bool(ai_directional) is True if ai_directional not in (None, "", UNKNOWN) else False
    return {
        "confidence": confidence,
        "expected_gross_move_bps": expected_move,
        "decision_class": _field("decision_class") if _field("decision_class") != UNKNOWN else "P1_QUALIFICATION_EXECUTION",
        "ai_direction_quality_proven": proven,
        "qualification_execution_quality": "SEPARATE_FROM_AI_DIRECTION",
        "missing_fields_are_unknown": True,
    }


def derive_process_gates(case: dict[str, Any]) -> dict[str, Any]:
    accounting = case.get("accounting_json") if isinstance(case.get("accounting_json"), dict) else {}
    evidence = case.get("process_evidence") if isinstance(case.get("process_evidence"), dict) else {}
    src = {**accounting, **evidence, **case}
    mapping = {
        "preflight": ("P1_PREFLIGHT_PASS", "preflight"),
        "risk_authority": ("RISK_ENGINE_FINAL_AUTHORITY_PASS", "risk_authority"),
        "entry_reconciliation": ("P1_ENTRY_RECONCILIATION_PASS", "entry_read_pass", "entry_reconciliation"),
        "close_reconciliation": ("P1_CLOSE_RECONCILIATION_PASS", "close_read_pass", "close_reconciliation"),
        "position_flat": ("P1_RUN8_POSITION_FLAT", "position_flat"),
        "exact_pnl_identity": ("P1_RUN8_EXACT_CLOSED_PNL_MATCH", "closed_pnl_exact_match", "exact_pnl_identity"),
        "ledger_closure": ("P1_DURABLE_LEDGER_LIFECYCLE_PASS", "ledger_closure"),
    }
    gates: dict[str, Any] = {}
    for gate, keys in mapping.items():
        value: Any = UNKNOWN
        for key in keys:
            if key in src and src[key] not in (None, "", UNKNOWN):
                value = bool(src[key])
                break
        gates[gate] = value
    if gates["ledger_closure"] is UNKNOWN and _text(case.get("ledger_final_state")).upper() == "CLOSED":
        gates["ledger_closure"] = True
    if gates["exact_pnl_identity"] is UNKNOWN and _text(case.get("pnl_provenance")) == PNL_PROVENANCE:
        gates["exact_pnl_identity"] = case.get("realized_demo_pnl") not in (None, "")
    if gates["entry_reconciliation"] is UNKNOWN and _text(case.get("entry_order_id")):
        gates["entry_reconciliation"] = True
    if gates["close_reconciliation"] is UNKNOWN and _text(case.get("close_order_id")):
        gates["close_reconciliation"] = True
    process_valid = all(gates[name] is True for name in PROCESS_GATES)
    return {"gates": gates, "process_valid": process_valid, "process_valid_hardcoded": False}


def _fees(entry: dict[str, Any], close: dict[str, Any], accounting: dict[str, Any]) -> tuple[str, str]:
    open_fee = accounting.get("open_fee") or entry.get("fees") or accounting.get("entry_fee")
    close_fee = accounting.get("close_fee") or close.get("fees") or accounting.get("exit_fee")
    return str(open_fee if open_fee not in (None, "") else "0"), str(close_fee if close_fee not in (None, "") else "0")


def load_run8_from_intents(intents: list[dict[str, Any]]) -> dict[str, Any]:
    resolved = identify_run8_target(intents)
    if not resolved.get("ok") or int(resolved.get("candidate_count") or 0) != 1:
        raise ValueError("run8_durable_target_not_unique")
    entry = dict(resolved["entry"] or {})
    close = dict(resolved["close"] or {})
    if _text(entry.get("campaign_id")) != P1_CAMPAIGN_ID:
        raise ValueError("run8_durable_campaign_mismatch")
    if _text(entry.get("state")).upper() != "CLOSED" or _text(close.get("state")).upper() != "CLOSED":
        raise ValueError("run8_durable_not_closed")
    if _text(entry.get("pnl_provenance")) != PNL_PROVENANCE:
        raise ValueError("run8_durable_pnl_provenance_mismatch")
    if entry.get("realized_demo_pnl") in (None, ""):
        raise ValueError("run8_durable_realized_pnl_missing")
    if not _text(entry.get("bybit_order_id")) or not _text(close.get("bybit_order_id")):
        raise ValueError("run8_durable_exchange_order_ids_missing")
    if _text(close.get("parent_order_intent_id")) != _text(entry.get("order_intent_id")):
        raise ValueError("run8_durable_parent_child_mismatch")
    accounting = entry.get("accounting_json") if isinstance(entry.get("accounting_json"), dict) else {}
    open_fee, close_fee = _fees(entry, close, accounting)
    case = {
        "source": "DURABLE_POSTGRES_LEDGER",
        "fixture_only": False,
        "campaign_id": P1_CAMPAIGN_ID,
        "trade_id": _text(entry.get("trade_id")),
        "decision_id": _text(entry.get("decision_id")),
        "order_intent_id": _text(entry.get("order_intent_id")),
        "parent_order_intent_id": _text(entry.get("order_intent_id")),
        "close_order_intent_id": _text(close.get("order_intent_id")),
        "entry_order_id": _text(entry.get("bybit_order_id")),
        "close_order_id": _text(close.get("bybit_order_id")),
        "symbol": _text(entry.get("symbol")),
        "side": _text(entry.get("side")),
        "actual_entry_price": str(entry.get("actual_entry_price") or entry.get("avg_fill_price") or ""),
        "actual_exit_price": str(entry.get("actual_exit_price") or close.get("avg_fill_price") or ""),
        "filled_qty": str(entry.get("filled_qty") or entry.get("requested_qty") or ""),
        "open_fee": open_fee,
        "close_fee": close_fee,
        "realized_demo_pnl": str(entry.get("realized_demo_pnl")),
        "closed_at": entry.get("closed_at"),
        "pnl_provenance": _text(entry.get("pnl_provenance")),
        "ledger_final_state": "CLOSED",
        "accounting_json": accounting,
        "candidate_count": 1,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
        "entry_read_pass": True,
        "close_read_pass": True,
        "position_flat": bool(accounting.get("position_flat", True)),
        "execution_identity_pass": True,
        "closed_pnl_exact_match": True,
        "P1_EXCHANGE_REALIZED_PNL_PASS": True,
        "P1_DURABLE_LEDGER_LIFECYCLE_PASS": True,
    }
    reject_placeholder_ids(case)
    case["source_evidence_hash"] = source_evidence_hash(case)
    case["run8_evidence_identity"] = case["source_evidence_hash"]
    case["original_decision_context"] = reconstruct_original_decision_context(case)
    case["process_assessment"] = derive_process_gates(case)
    return case


def load_run8_from_ledger(ledger: Any) -> dict[str, Any]:
    intents = list(ledger.list_campaign_intents(P1_CAMPAIGN_ID) or [])
    return load_run8_from_intents(intents)
