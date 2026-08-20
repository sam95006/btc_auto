"""P2.1 evidence-truth tests — no synthetic PASS, no exchange writes."""
from __future__ import annotations

from backend.nexus_demo_execution.p1_qualification import P1_CAMPAIGN_ID
from backend.nexus_demo_execution.p2_run8_durable_loader import (
    UNKNOWN,
    derive_process_gates,
    load_run8_from_intents,
    parse_strict_bool,
    reconstruct_original_decision_context,
)
from backend.nexus_demo_execution.p2_run8_learning_closure import PNL_PROVENANCE


def _base_intents(**accounting_extra: object) -> list[dict]:
    accounting = {
        "open_fee": "0.03535521",
        "close_fee": "0.03535521",
        **accounting_extra,
    }
    return [
        {
            "order_intent_id": "p1ent_run8_durable",
            "decision_id": "p1dec_run8_real_aaaaaaaa",
            "trade_id": "p1trd_run8_real_bbbbbbbb",
            "campaign_id": P1_CAMPAIGN_ID,
            "symbol": "BTCUSDT",
            "side": "Buy",
            "requested_qty": "0.001",
            "reduce_only": False,
            "state": "CLOSED",
            "bybit_order_id": "entry-oid-run8-real",
            "filled_qty": "0.001",
            "parent_order_intent_id": None,
            "actual_entry_price": "64282.2",
            "actual_exit_price": "64282.2",
            "realized_demo_pnl": "-0.07071042",
            "pnl_provenance": PNL_PROVENANCE,
            "closed_at": "2026-08-18T07:05:00+00:00",
            "accounting_json": accounting,
        },
        {
            "order_intent_id": "p1cls_run8_durable",
            "decision_id": "p1dec_run8_real_aaaaaaaa",
            "trade_id": "p1trd_run8_real_bbbbbbbb",
            "campaign_id": P1_CAMPAIGN_ID,
            "symbol": "BTCUSDT",
            "side": "Sell",
            "requested_qty": "0.001",
            "reduce_only": True,
            "state": "CLOSED",
            "bybit_order_id": "close-oid-run8-real",
            "filled_qty": "0.001",
            "parent_order_intent_id": "p1ent_run8_durable",
            "avg_fill_price": "64282.2",
        },
    ]


def test_missing_position_flat_does_not_become_true():
    case = load_run8_from_intents(_base_intents())
    assert case["position_flat"] == UNKNOWN
    assert case["process_assessment"]["gates"]["position_flat"]["value"] == UNKNOWN


def test_order_id_alone_does_not_prove_reconciliation():
    case = load_run8_from_intents(_base_intents())
    assert case["entry_order_id"]
    assert case["close_order_id"]
    assert case["process_assessment"]["gates"]["entry_reconciliation"]["value"] == UNKNOWN
    assert case["process_assessment"]["gates"]["close_reconciliation"]["value"] == UNKNOWN


def test_provenance_and_pnl_alone_do_not_prove_exact_closed_pnl_identity():
    case = load_run8_from_intents(_base_intents())
    assert case["pnl_provenance"] == PNL_PROVENANCE
    assert case["realized_demo_pnl"]
    assert case["process_assessment"]["gates"]["exact_pnl_identity"]["value"] == UNKNOWN


def test_false_bool_string_remains_false():
    assert parse_strict_bool("false") is False
    assert parse_strict_bool("true") is True
    assert parse_strict_bool(UNKNOWN) is None
    ctx = reconstruct_original_decision_context(
        {"accounting_json": {"ai_directional_decision": "false"}, "original_decision_context": {}}
    )
    assert ctx["ai_directional_decision"] is False
    assert ctx["ai_direction_quality_proven"] is False


def test_accounting_actual_qty_preferred_over_requested_qty():
    intents = _base_intents(actual_qty="0.002")
    intents[0]["filled_qty"] = None
    intents[0]["requested_qty"] = "0.001"
    case = load_run8_from_intents(intents)
    assert case["filled_qty"] == "0.002"
    assert case["filled_qty_source"] == "accounting_json.actual_qty"


def test_unknown_process_evidence_stays_unknown():
    case = load_run8_from_intents(_base_intents())
    for name in ("preflight", "risk_authority", "entry_reconciliation", "close_reconciliation", "position_flat", "exact_pnl_identity"):
        gate = case["process_assessment"]["gates"][name]
        assert gate["value"] == UNKNOWN
        assert gate["source"] is None
        assert gate["source_field"] is None
    assert case["process_assessment"]["process_valid"] is False
    assert case["process_assessment"]["process_validation_status"] == "INCOMPLETE_EVIDENCE"
    assert case["entry_read_pass"] == UNKNOWN
    assert case["close_read_pass"] == UNKNOWN
    assert case["execution_identity_pass"] == UNKNOWN
    assert case["closed_pnl_exact_match"] == UNKNOWN
    assert case["P1_EXCHANGE_REALIZED_PNL_PASS"] == UNKNOWN
    assert case["P1_DURABLE_LEDGER_LIFECYCLE_PASS"] == UNKNOWN


def test_complete_durable_gates_are_sourced_not_hardcoded():
    case = load_run8_from_intents(
        _base_intents(
            P1_PREFLIGHT_PASS=True,
            RISK_ENGINE_FINAL_AUTHORITY_PASS=True,
            P1_ENTRY_RECONCILIATION_PASS=True,
            P1_CLOSE_RECONCILIATION_PASS=True,
            position_flat=True,
            P1_RUN8_EXACT_CLOSED_PNL_MATCH=True,
            P1_DURABLE_LEDGER_LIFECYCLE_PASS=True,
        )
    )
    assessment = case["process_assessment"]
    assert assessment["process_valid"] is True
    assert assessment["process_valid_hardcoded"] is False
    assert assessment["process_validation_status"] == "COMPLETE"
    assert assessment["gates"]["entry_reconciliation"] == {
        "value": True,
        "source": "durable_accounting_json",
        "source_field": "P1_ENTRY_RECONCILIATION_PASS",
    }


def test_failed_gate_is_not_overwritten_to_true():
    assessment = derive_process_gates({"position_flat": False, "ledger_final_state": "CLOSED"})
    assert assessment["gates"]["position_flat"]["value"] is False
    assert assessment["process_valid"] is False
