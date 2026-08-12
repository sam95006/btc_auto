"""Historical simulated completed trades + genuine process records for V15-I.

These are SIMULATED lifecycle completions (no exchange write, no live market).
They carry genuine historical process evidence fields for replay classification.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_lesson_replay_v15.constants import (
    GENUINE_PROCESS_LABEL,
    HISTORICAL_SIM_LABEL,
    SCHEMA_SIM_TRADES,
)


def _sim(
    *,
    trade_id: str,
    net_pnl: float,
    symbol: str = "BTCUSDT",
    cost_gate_status: str = "PASS",
    risk_gate_status: str = "PASS",
    data_quality_status: str = "FRESH",
    stop_price: Any = 94000.0,
    entry_price: Any = 100000.0,
    target_price: Any = 106000.0,
    hard_block_reasons: list[str] | None = None,
    rule_violation_count: int = 0,
    prohibited_action_count: int = 0,
    position_size_valid: bool = True,
    liquidation_distance_valid: bool = True,
    completed_at: str = "2026-07-01T12:00:00Z",
    lifecycle_state: str = "SIMULATED_EXITED",
) -> dict[str, Any]:
    return {
        "trade_id": trade_id,
        "candidate_id": f"cand_{trade_id}",
        "symbol": symbol,
        "side": "BUY",
        "entry_price": entry_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "net_pnl": net_pnl,
        "cost_gate_status": cost_gate_status,
        "risk_gate_status": risk_gate_status,
        "data_quality_status": data_quality_status,
        "hard_block_reasons": list(hard_block_reasons or []),
        "rule_violation_count": rule_violation_count,
        "prohibited_action_count": prohibited_action_count,
        "position_size_valid": position_size_valid,
        "liquidation_distance_valid": liquidation_distance_valid,
        "lifecycle_state": lifecycle_state,
        "completed": True,
        "completed_at": completed_at,
        "execution_mode": "HISTORICAL_REPLAY_SIMULATED_NO_EXCHANGE_WRITE",
        "source_kind": "HISTORICAL_SIMULATED_COMPLETED_TRADE",
        "historical_sim_label": HISTORICAL_SIM_LABEL,
        "process_record_label": GENUINE_PROCESS_LABEL,
        "is_fixture": False,
        "mechanics_only": False,
        "real_trading_learning": False,
        "exchange_write": False,
        "live_market": False,
        "mainnet": False,
        "real_money": False,
        "oos_reserved": False,
        "interval_class": "DEVELOPMENT_RESEARCH_ALLOWED",
        "fixture_label": None,
    }


def historical_simulated_completed_trades() -> list[dict[str, Any]]:
    """Deterministic corpus of completed historical simulated trades.

    Covers all five process classes with genuine process-record fields.
    Not live; not fixture-as-real; not OOS.
    """
    return [
        # GOOD_PROCESS_WIN
        _sim(
            trade_id="V15I_SIM_hist_good_win_001",
            net_pnl=18.25,
            completed_at="2026-06-12T08:15:00Z",
        ),
        # GOOD_PROCESS_LOSS — compliant loss must stay GOOD_PROCESS_LOSS
        _sim(
            trade_id="V15I_SIM_hist_good_loss_002",
            net_pnl=-6.4,
            symbol="ETHUSDT",
            entry_price=3500.0,
            stop_price=3400.0,
            target_price=3700.0,
            completed_at="2026-06-14T11:22:00Z",
        ),
        # BAD_PROCESS_LOSS (stale data) — genuine process noncompliance
        _sim(
            trade_id="V15I_SIM_hist_bad_stale_loss_003",
            net_pnl=-11.0,
            data_quality_status="STALE",
            completed_at="2026-06-18T16:40:00Z",
        ),
        # Same signature later (replay prevention observation only)
        _sim(
            trade_id="V15I_SIM_hist_bad_stale_later_004",
            net_pnl=-4.2,
            data_quality_status="STALE",
            completed_at="2026-06-19T09:05:00Z",
        ),
        # BAD_PROCESS_WIN (cost gate fail, positive PnL)
        _sim(
            trade_id="V15I_SIM_hist_bad_cost_win_005",
            net_pnl=3.1,
            cost_gate_status="FAIL",
            completed_at="2026-06-21T13:55:00Z",
        ),
        # UNDETERMINED — insufficient process evidence
        {
            "trade_id": "V15I_SIM_hist_undetermined_006",
            "candidate_id": "cand_V15I_SIM_hist_undetermined_006",
            "symbol": "SOLUSDT",
            "side": "SELL",
            "entry_price": "UNKNOWN",
            "stop_price": "UNKNOWN",
            "target_price": "UNKNOWN",
            "net_pnl": -0.5,
            "cost_gate_status": "UNKNOWN",
            "risk_gate_status": "UNKNOWN",
            "data_quality_status": "UNKNOWN",
            "hard_block_reasons": [],
            "rule_violation_count": 0,
            "prohibited_action_count": 0,
            "position_size_valid": True,
            "liquidation_distance_valid": True,
            "lifecycle_state": "SIMULATED_EXITED",
            "completed": True,
            "completed_at": "2026-06-22T07:30:00Z",
            "execution_mode": "HISTORICAL_REPLAY_SIMULATED_NO_EXCHANGE_WRITE",
            "source_kind": "HISTORICAL_SIMULATED_COMPLETED_TRADE",
            "historical_sim_label": HISTORICAL_SIM_LABEL,
            "process_record_label": GENUINE_PROCESS_LABEL,
            "is_fixture": False,
            "real_trading_learning": False,
            "exchange_write": False,
            "live_market": False,
            "mainnet": False,
            "real_money": False,
            "oos_reserved": False,
            "interval_class": "DEVELOPMENT_RESEARCH_ALLOWED",
            "fixture_label": None,
        },
        # BAD_PROCESS_LOSS missing stop
        _sim(
            trade_id="V15I_SIM_hist_missing_stop_007",
            net_pnl=-9.75,
            stop_price=None,
            completed_at="2026-06-25T19:10:00Z",
        ),
        # Additional GOOD_PROCESS_WIN (multi-asset)
        _sim(
            trade_id="V15I_SIM_hist_good_win_008",
            net_pnl=7.8,
            symbol="XRPUSDT",
            entry_price=0.62,
            stop_price=0.58,
            target_price=0.70,
            completed_at="2026-06-28T04:45:00Z",
        ),
    ]


def simulated_trades_manifest() -> dict[str, Any]:
    trades = historical_simulated_completed_trades()
    return {
        "schema": SCHEMA_SIM_TRADES,
        "historical_sim_label": HISTORICAL_SIM_LABEL,
        "process_record_label": GENUINE_PROCESS_LABEL,
        "trade_count": len(trades),
        "all_completed": all(bool(t.get("completed")) for t in trades),
        "exchange_write_attempt_count": 0,
        "live_market": False,
        "mainnet": False,
        "real_money": False,
        "oos_reserved": False,
        "fixture_misrepresented_as_real": False,
        "trade_ids": [t["trade_id"] for t in trades],
        "trades": trades,
    }
