"""H4 Edge Research V1 — preregistered hypotheses (checksum before execution).

Thresholds derived from prior V3 Walk-forward / cost-gate starvation evidence only.
Do NOT derive thresholds from consumed H3 closed historical holdout.
"""
from __future__ import annotations

from typing import Any

# Development data may use prior V2/V3 research span only (not holdout / not September OOS).
H4_DEV_START_MS = 1_739_007_000_000
H4_DEV_END_MS = 1_785_663_000_000

# Advancement gates (preregistered; immutable after results visible).
H4_GATES: dict[str, Any] = {
    "min_completed_trades": 60,
    "min_walk_forward_folds": 3,
    "min_net_expectancy": 0.0,
    "min_base_profit_factor": 1.15,
    "min_adverse_profit_factor": 1.00,
    "max_symbol_share": 0.55,
    "max_fold_profit_share": 0.70,
    "max_drawdown_abs": 50.0,
    "lookahead_violation_count_max": 0,
    "invalid_position_size_count_max": 0,
    "liquidation_policy_breach_count_max": 0,
    "risk_limit_breach_count_max": 0,
}

HYPOTHESES_H4: list[dict[str, Any]] = [
    {
        "hypothesis_id": "H4A_EVENT_RETEST_CONTINUATION",
        "family": "H4",
        "variant": "A",
        "cohort": "trend_following|TRENDING_DOWN|Sell",
        "entry_logic": "60m_displacement_then_15m_retest_reject",
        "confirmation_logic": (
            "240m TRENDING_DOWN; 60m structural displacement >= min_disp_atr; "
            "15m retest toward structure then reject; no immediate breakout chase"
        ),
        "exit_logic": "vol_normalized_structural_geometry",
        "churn_logic": "one_per_event_level; cooldown=28",
        "parameter_values": {
            "min_move_to_cost": 2.8,
            "cooldown_15m_bars": 28,
            "min_disp_atr": 1.2,
            "max_chase_atr": 0.35,
            "stop_atr": 0.9,
            "target_atr": 1.8,
            "retest_lookback_15m": 10,
            "min_holding_expectation_bars": 10,
        },
        "threshold_rationale": (
            "Stricter than H3 min_move_to_cost 2.5 based on V3 cost-gate starvation "
            "(ENTRY_TOO_LATE / TARGET_TOO_CLOSE). Retest required to avoid breakout chase "
            "that failed portability on closed historical."
        ),
        "expected_failure_mode": "INSUFFICIENT_SAMPLE or REJECTED_UNSTABLE_ACROSS_FOLDS",
        "created_before_evaluation": True,
        "requires_microstructure": False,
        "forbidden_sources_for_thresholds": [
            "H3_CLOSED_HISTORICAL_HOLDOUT_V1_RESERVED",
            "OOS_H3_UNTOUCHED_V1_RESERVED",
        ],
    },
    {
        "hypothesis_id": "H4B_VOLATILITY_NORMALIZED_CONTINUATION",
        "family": "H4",
        "variant": "B",
        "cohort": "trend_following|TRENDING_DOWN|Sell",
        "entry_logic": "atr_normalized_continuation_with_late_entry_reject",
        "confirmation_logic": (
            "240m TRENDING_DOWN; stop/target ATR-normalized; reject insufficient reachable "
            "move after costs; reject excessive stop width; reject late extension"
        ),
        "exit_logic": "atr_normalized_tp_stop",
        "churn_logic": "cooldown=32",
        "parameter_values": {
            "min_move_to_cost": 3.0,
            "cooldown_15m_bars": 32,
            "stop_atr": 0.75,
            "target_atr": 2.0,
            "max_stop_atr": 1.1,
            "max_extension_atr": 1.0,
            "min_rr_after_cost_proxy": 1.5,
            "min_holding_expectation_bars": 12,
        },
        "threshold_rationale": (
            "Raises economic floor vs H3 and caps stop width / late extension using V3 "
            "starvation classes COST_TOO_HIGH_FOR_TIMEFRAME and ENTRY_TOO_LATE."
        ),
        "expected_failure_mode": "REJECTED_COST_DOMINATED or INSUFFICIENT_SAMPLE",
        "created_before_evaluation": True,
        "requires_microstructure": False,
        "forbidden_sources_for_thresholds": [
            "H3_CLOSED_HISTORICAL_HOLDOUT_V1_RESERVED",
            "OOS_H3_UNTOUCHED_V1_RESERVED",
        ],
    },
    {
        "hypothesis_id": "H4C_OI_FUNDING_CONFIRMED_CONTINUATION",
        "family": "H4",
        "variant": "C",
        "cohort": "trend_following|TRENDING_DOWN|Sell",
        "entry_logic": "continuation_with_non_contradictory_oi_and_funding",
        "confirmation_logic": (
            "H4A-like structure plus real OI not collapsing against short; "
            "extreme positive funding blocks; missing OI/funding blocks hypothesis"
        ),
        "exit_logic": "vol_normalized_structural_geometry",
        "churn_logic": "cooldown=28",
        "parameter_values": {
            "min_move_to_cost": 2.8,
            "cooldown_15m_bars": 28,
            "min_disp_atr": 1.0,
            "stop_atr": 0.9,
            "target_atr": 1.8,
            "oi_collapse_max_pct": -0.02,
            "funding_abs_max": 0.0008,
            "min_holding_expectation_bars": 10,
        },
        "threshold_rationale": (
            "Uses V3 H3G-style micro filter floors; MISSING OI/funding must block rather "
            "than invent values. Thresholds not taken from consumed holdout subgroups."
        ),
        "expected_failure_mode": "DATA_INVALID or INSUFFICIENT_SAMPLE",
        "created_before_evaluation": True,
        "requires_microstructure": True,
        "enrichment": ["open_interest", "funding"],
        "forbidden_sources_for_thresholds": [
            "H3_CLOSED_HISTORICAL_HOLDOUT_V1_RESERVED",
            "OOS_H3_UNTOUCHED_V1_RESERVED",
        ],
    },
]
