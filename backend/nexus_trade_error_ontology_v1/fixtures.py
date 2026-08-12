"""Control fixtures for V16-A Trade Error Ontology (mechanics only)."""
from __future__ import annotations

from typing import Any

from backend.nexus_trade_error_ontology_v1.constants import CONTROL_FIXTURE_LABEL


def _base(**overrides: Any) -> dict[str, Any]:
    packet: dict[str, Any] = {
        "trade_id": "V16A_FIX_base",
        "source_kind": "control_fixture",
        "is_fixture": True,
        "fixture_label": CONTROL_FIXTURE_LABEL,
        "real_trading_learning": False,
        "mechanics_only": True,
        "exchange_write": False,
        "mainnet": False,
        "real_money": False,
        "entry_price": 100.0,
        "stop_price": 95.0,
        "target_price": 110.0,
        "cost_gate_status": "PASS",
        "risk_gate_status": "PASS",
        "data_quality_status": "OK",
        "position_size_valid": True,
        "liquidation_distance_valid": True,
        "rule_violation_count": 0,
        "prohibited_action_count": 0,
        "hard_block_reasons": [],
        "entry_rule_compliance": "PASS",
        "exit_rule_compliance": "PASS",
        "net_pnl": 0.0,
        "external_shock_flag": False,
    }
    packet.update(overrides)
    return packet


def labeled_fixture_controls() -> list[dict[str, Any]]:
    return [
        _base(
            trade_id="V16A_FIX_good_win",
            net_pnl=12.5,
        ),
        _base(
            trade_id="V16A_FIX_good_loss",
            net_pnl=-8.0,
        ),
        _base(
            trade_id="V16A_FIX_bad_cost_win",
            net_pnl=15.0,
            cost_gate_status="FAIL",
        ),
        _base(
            trade_id="V16A_FIX_bad_risk_loss",
            net_pnl=-20.0,
            risk_gate_status="EXCEEDED",
        ),
        _base(
            trade_id="V16A_FIX_insufficient",
            net_pnl=-3.0,
            stop_price="UNKNOWN",
            cost_gate_status="UNKNOWN",
            data_quality_status="UNKNOWN",
            entry_price="UNKNOWN",
            target_price="UNKNOWN",
        ),
        _base(
            trade_id="V16A_FIX_unavoidable_shock",
            net_pnl=-50.0,
            external_shock_flag=True,
            external_shock_type="flash_crash",
            supporting_evidence_ids=["evt:flash_crash:sim"],
        ),
        _base(
            trade_id="V16A_FIX_bad_stop_win",
            net_pnl=9.0,
            stop_price="MISSING",
        ),
        _base(
            trade_id="V16A_FIX_stale_data_loss",
            net_pnl=-4.0,
            data_quality_status="STALE",
        ),
        _base(
            trade_id="V16A_FIX_shock_with_cost_fault",
            net_pnl=-12.0,
            external_shock_flag=True,
            external_shock_type="exchange_halt",
            cost_gate_status="FAIL",
        ),
    ]


def expected_class_by_trade_id() -> dict[str, str]:
    return {
        "V16A_FIX_good_win": "GOOD_PROCESS_WIN",
        "V16A_FIX_good_loss": "GOOD_PROCESS_LOSS",
        "V16A_FIX_bad_cost_win": "BAD_PROCESS_WIN",
        "V16A_FIX_bad_risk_loss": "BAD_PROCESS_LOSS",
        "V16A_FIX_insufficient": "INSUFFICIENT_EVIDENCE",
        "V16A_FIX_unavoidable_shock": "UNAVOIDABLE_SHOCK",
        "V16A_FIX_bad_stop_win": "BAD_PROCESS_WIN",
        "V16A_FIX_stale_data_loss": "BAD_PROCESS_LOSS",
        # Shock + process fault → process fault wins (BAD), not UNAVOIDABLE.
        "V16A_FIX_shock_with_cost_fault": "BAD_PROCESS_LOSS",
    }
