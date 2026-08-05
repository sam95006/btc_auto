"""Labeled control fixtures for V15-I Lesson Replay Lab.

These packets prove classification / replay mechanics only.
They must NEVER be labeled as real policy-effect / real trading learning evidence.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_lesson_replay_v15.constants import (
    CONTROL_FIXTURE_LABEL,
    SCHEMA_FIXTURES,
)


def _base(
    *,
    trade_id: str,
    net_pnl: float,
    cost_gate_status: str = "PASS",
    risk_gate_status: str = "PASS",
    data_quality_status: str = "FRESH",
    stop_price: Any = 95000.0,
    hard_block_reasons: list[str] | None = None,
    rule_violation_count: int = 0,
    prohibited_action_count: int = 0,
    position_size_valid: bool = True,
    liquidation_distance_valid: bool = True,
) -> dict[str, Any]:
    return {
        "trade_id": trade_id,
        "candidate_id": f"cand_{trade_id}",
        "symbol": "BTCUSDT",
        "entry_price": 100000.0,
        "stop_price": stop_price,
        "target_price": 105000.0,
        "net_pnl": net_pnl,
        "cost_gate_status": cost_gate_status,
        "risk_gate_status": risk_gate_status,
        "data_quality_status": data_quality_status,
        "hard_block_reasons": list(hard_block_reasons or []),
        "rule_violation_count": rule_violation_count,
        "prohibited_action_count": prohibited_action_count,
        "position_size_valid": position_size_valid,
        "liquidation_distance_valid": liquidation_distance_valid,
        "control_fixture_label": "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE",
        "fixture_label": CONTROL_FIXTURE_LABEL,
        "source_kind": "LABELED_FIXTURE_CONTROL",
        "mechanics_only": True,
        "real_trading_learning": False,
        "is_fixture": True,
        "exchange_write": False,
        "live_market": False,
    }


def labeled_fixture_controls() -> list[dict[str, Any]]:
    """Deterministic fixture set covering all five process classes."""
    return [
        _base(trade_id="V15I_FIX_good_win", net_pnl=12.5),
        _base(trade_id="V15I_FIX_good_loss", net_pnl=-8.0),
        _base(
            trade_id="V15I_FIX_bad_stale_loss",
            net_pnl=-15.0,
            data_quality_status="STALE",
        ),
        _base(
            trade_id="V15I_FIX_bad_stale_later",
            net_pnl=-3.0,
            data_quality_status="STALE",
        ),
        _base(
            trade_id="V15I_FIX_bad_cost_win",
            net_pnl=4.0,
            cost_gate_status="FAIL",
        ),
        {
            "trade_id": "V15I_FIX_undetermined",
            "candidate_id": "cand_V15I_FIX_undetermined",
            "symbol": "BTCUSDT",
            "entry_price": "UNKNOWN",
            "stop_price": "UNKNOWN",
            "target_price": "UNKNOWN",
            "net_pnl": -1.0,
            "cost_gate_status": "UNKNOWN",
            "risk_gate_status": "UNKNOWN",
            "data_quality_status": "UNKNOWN",
            "hard_block_reasons": [],
            "rule_violation_count": 0,
            "prohibited_action_count": 0,
            "position_size_valid": True,
            "liquidation_distance_valid": True,
            "control_fixture_label": "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE",
            "fixture_label": CONTROL_FIXTURE_LABEL,
            "source_kind": "LABELED_FIXTURE_CONTROL",
            "mechanics_only": True,
            "real_trading_learning": False,
            "is_fixture": True,
            "exchange_write": False,
            "live_market": False,
        },
        _base(
            trade_id="V15I_FIX_missing_stop",
            net_pnl=-2.0,
            stop_price=None,
        ),
    ]


def fixture_controls_manifest() -> dict[str, Any]:
    pkts = labeled_fixture_controls()
    return {
        "schema": SCHEMA_FIXTURES,
        "label": CONTROL_FIXTURE_LABEL,
        "fixture_count": len(pkts),
        "clearly_labelled": True,
        "real_trading_learning": False,
        "real_policy_effect_proof": False,
        "trade_ids": [p["trade_id"] for p in pkts],
        "packets": pkts,
    }


def prohibited_effect_probe() -> dict[str, Any]:
    return {
        "requested_effect": "increase_leverage",
        "ai_or_lesson_requested_prohibited_action": True,
        "deterministic_risk_rejected": True,
        "order_or_policy_mutation": False,
        "fixture_label": CONTROL_FIXTURE_LABEL,
    }
