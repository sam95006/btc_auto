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
GATE_FIELDS: dict[str, tuple[str, ...]] = {
    "preflight": ("P1_PREFLIGHT_PASS", "preflight"),
    "risk_authority": ("RISK_ENGINE_FINAL_AUTHORITY_PASS", "risk_authority"),
    "entry_reconciliation": ("P1_ENTRY_RECONCILIATION_PASS", "entry_read_pass", "entry_reconciliation"),
    "close_reconciliation": ("P1_CLOSE_RECONCILIATION_PASS", "close_read_pass", "close_reconciliation"),
    "position_flat": ("P1_RUN8_POSITION_FLAT", "position_flat"),
    "exact_pnl_identity": ("P1_RUN8_EXACT_CLOSED_PNL_MATCH", "closed_pnl_exact_match", "exact_pnl_identity"),
    "ledger_closure": ("P1_DURABLE_LEDGER_LIFECYCLE_PASS", "ledger_closure"),
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dec(value: Any) -> Decimal | None:
    if value in (None, "", UNKNOWN):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_strict_bool(value: Any) -> bool | None:
    """Parse booleans without treating non-empty strings as True."""
    if value is True:
        return True
    if value is False:
        return False
    if value in (None, "", UNKNOWN):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
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
    parsed_ai = parse_strict_bool(ai_directional)
    proven = parsed_ai is True
    return {
        "confidence": confidence,
        "expected_gross_move_bps": expected_move,
        "decision_class": _field("decision_class") if _field("decision_class") != UNKNOWN else "P1_QUALIFICATION_EXECUTION",
        "ai_directional_decision": parsed_ai if parsed_ai is not None else UNKNOWN,
        "ai_direction_quality_proven": proven,
        "qualification_execution_quality": "SEPARATE_FROM_AI_DIRECTION",
        "missing_fields_are_unknown": True,
    }


def _unknown_gate() -> dict[str, Any]:
    return {"value": UNKNOWN, "source": None, "source_field": None}


def _gate(value: Any, source: str, source_field: str) -> dict[str, Any]:
    return {"value": value, "source": source, "source_field": source_field}


def _source_layer(key: str, accounting: dict[str, Any], evidence: dict[str, Any], case: dict[str, Any]) -> str:
    if key in accounting:
        return "durable_accounting_json"
    if key in evidence:
        return "durable_process_evidence"
    if key in case:
        return "durable_intent_row"
    return "durable_evidence"


def derive_process_gates(case: dict[str, Any]) -> dict[str, Any]:
    accounting = case.get("accounting_json") if isinstance(case.get("accounting_json"), dict) else {}
    evidence = case.get("process_evidence") if isinstance(case.get("process_evidence"), dict) else {}
    layers = (accounting, evidence, case)
    gates: dict[str, Any] = {}
    for gate, keys in GATE_FIELDS.items():
        found = _unknown_gate()
        for key in keys:
            for layer in layers:
                if key not in layer:
                    continue
                parsed = parse_strict_bool(layer.get(key))
                if parsed is None:
                    continue
                found = _gate(parsed, _source_layer(key, accounting, evidence, case), key)
                break
            if found["value"] is not UNKNOWN:
                break
        gates[gate] = found
    if gates["ledger_closure"]["value"] is UNKNOWN and _text(case.get("ledger_final_state")).upper() == "CLOSED":
        gates["ledger_closure"] = _gate(True, "durable_ledger_state", "ledger_final_state")
    unknown = [name for name in PROCESS_GATES if gates[name]["value"] is UNKNOWN]
    failed = [name for name in PROCESS_GATES if gates[name]["value"] is False]
    if unknown:
        status = "INCOMPLETE_EVIDENCE"
        process_valid = False
    elif failed:
        status = "FAILED_GATES"
        process_valid = False
    else:
        status = "COMPLETE"
        process_valid = True
    return {
        "gates": gates,
        "process_valid": process_valid,
        "process_valid_hardcoded": False,
        "process_validation_status": status,
        "unknown_gates": unknown,
        "failed_gates": failed,
    }


def resolve_filled_qty(entry: dict[str, Any], accounting: dict[str, Any]) -> tuple[str, str]:
    if accounting.get("actual_qty") not in (None, ""):
        return str(accounting["actual_qty"]), "accounting_json.actual_qty"
    if entry.get("filled_qty") not in (None, ""):
        return str(entry["filled_qty"]), "filled_qty"
    if entry.get("requested_qty") not in (None, ""):
        return str(entry["requested_qty"]), "requested_qty"
    return "", "MISSING"


def _optional_copied_bool(accounting: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key not in accounting:
            continue
        parsed = parse_strict_bool(accounting.get(key))
        if parsed is not None:
            return parsed
    return UNKNOWN


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
    filled_qty, filled_qty_source = resolve_filled_qty(entry, accounting)
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
        "filled_qty": filled_qty,
        "filled_qty_source": filled_qty_source,
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
        "entry_read_pass": _optional_copied_bool(accounting, "entry_read_pass", "P1_ENTRY_RECONCILIATION_PASS"),
        "close_read_pass": _optional_copied_bool(accounting, "close_read_pass", "P1_CLOSE_RECONCILIATION_PASS"),
        "position_flat": _optional_copied_bool(accounting, "position_flat", "P1_RUN8_POSITION_FLAT"),
        "execution_identity_pass": _optional_copied_bool(accounting, "execution_identity_pass"),
        "closed_pnl_exact_match": _optional_copied_bool(accounting, "closed_pnl_exact_match", "P1_RUN8_EXACT_CLOSED_PNL_MATCH"),
        "P1_EXCHANGE_REALIZED_PNL_PASS": _optional_copied_bool(accounting, "P1_EXCHANGE_REALIZED_PNL_PASS"),
        "P1_DURABLE_LEDGER_LIFECYCLE_PASS": _optional_copied_bool(accounting, "P1_DURABLE_LEDGER_LIFECYCLE_PASS"),
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
