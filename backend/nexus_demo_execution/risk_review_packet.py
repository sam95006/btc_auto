"""Founder Risk Review packet — never auto-sets RISK_REVIEWED."""
from __future__ import annotations

from typing import Any

from backend.nexus_demo_execution.session_limits import (
    MIN_NET_REWARD_RISK_RATIO,
    MIN_NET_REWARD_TO_COST,
)


def build_risk_review_packet(
    *,
    walk_forward: dict[str, Any],
    oos: dict[str, Any],
    diagnostic_ab: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a packet for Founder sign-off. Status remains PENDING until explicit sign."""
    oos_trades = int(oos.get("simulated_trade_count") or oos.get("oos_simulated_trades") or 0)
    oos_status = str(oos.get("oos_status") or "")
    path_source = str(oos.get("path_source") or "")
    synth = int(oos.get("synthetic_forced_trade_count") or 0)
    ready = (
        path_source == "REAL_HISTORICAL_MARKET_DATA"
        and synth == 0
        and oos_trades >= 30
        and oos.get("net_pnl") is not None
        and oos.get("profit_factor") is not None
        and oos.get("expectancy") is not None
        and oos.get("maximum_drawdown") is not None
        and not bool(oos.get("look_ahead_contamination"))
        and oos_status == "OOS_PERFORMANCE_VALIDATED"
    )
    return {
        "packet_version": "geometry_risk_review_v1",
        "risk_review_status": "RISK_REVIEW_PENDING_FOUNDER",
        "risk_reviewed": False,
        "packet_ready": ready,
        "sample_size": oos_trades,
        "walk_forward_sample_size": int(walk_forward.get("simulated_trade_count") or 0),
        "symbols": "synthetic_mix_40" if diagnostic_ab else "UNKNOWN",
        "regimes": ["TREND_UP", "TREND_DOWN", "RANGE"],
        "strategies": ["STRUCT_SWING"],
        "trade_frequency": "offline_event_sim",
        "net_expectancy": oos.get("expectancy"),
        "profit_factor": oos.get("profit_factor"),
        "maximum_drawdown": oos.get("maximum_drawdown"),
        "net_pnl": oos.get("net_pnl"),
        "win_rate": oos.get("win_rate"),
        "largest_loss": None,
        "consecutive_losses": None,
        "fee_sensitivity": {
            "standard_conservative": oos.get("fees"),
            "note": "Qualification fails if only optimistic costs pass",
        },
        "slippage_sensitivity": {"observed": oos.get("slippage_cost")},
        "funding_sensitivity": {"observed": oos.get("funding")},
        "cost_stress": {
            "spread_cost": oos.get("spread_cost"),
            "adverse_first_intrabar": True,
        },
        "floors_unchanged": {
            "MIN_NET_REWARD_RISK_RATIO": MIN_NET_REWARD_RISK_RATIO,
            "MIN_NET_REWARD_TO_COST": MIN_NET_REWARD_TO_COST,
        },
        "failure_scenarios": [
            "LOOK_AHEAD_CONTAMINATION",
            "COST_DOMINATED_AFTER_STRESS",
            "INSUFFICIENT_OOS_SAMPLE",
            "SINGLE_SYMBOL_CONCENTRATION",
            "SINGLE_REGIME_CONCENTRATION",
        ],
        "kill_switch_limits": {
            "session_loss_limit_usdt": "FOUNDER_TO_SET",
            "max_consecutive_losses": "FOUNDER_TO_SET",
            "max_drawdown_fraction": "FOUNDER_TO_SET",
        },
        "recommended_canary_duration": "FOUNDER_TO_SET_AFTER_SIGN_OFF",
        "recommended_maximum_entries": "FOUNDER_TO_SET_AFTER_SIGN_OFF",
        "recommended_session_loss_limit": "FOUNDER_TO_SET_AFTER_SIGN_OFF",
        "shadow_prerequisite": "Founder explicit RISK_REVIEWED sign-off required before Shadow",
        "oos_status": oos.get("oos_status"),
        "walk_forward_status": walk_forward.get("walk_forward_status"),
        "look_ahead_contamination": bool(oos.get("look_ahead_contamination")),
    }
