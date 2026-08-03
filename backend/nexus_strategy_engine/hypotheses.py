"""Generate up to 12 preregistered development hypotheses across ≥4 families."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_demo_execution.closed_historical_registry import (
    RESEARCH_V2_V3_END_MS,
    RESEARCH_V2_V3_START_MS,
    SEPTEMBER_OOS_END_MS,
    SEPTEMBER_OOS_START_MS,
)
from backend.nexus_strategy_engine.components import COMPONENT_IDS, component_registry
from backend.nexus_strategy_engine.constants import (
    MAX_DEVELOPMENT_HYPOTHESES,
    MIN_STRATEGY_FAMILIES,
)
from backend.nexus_strategy_engine.strategy_spec import freeze_spec

DEV_INTERVAL = "DEV_RESEARCH_V2_V3_SPAN"
EXCLUDED = [
    "SEPTEMBER_H3_OOS",
    "CONSUMED_FAILED_HOLDOUT",
    "H3_CLOSED_HISTORICAL_HOLDOUT",
]


def _base(
    *,
    strategy_id: str,
    family: str,
    component_id: str,
    mechanism: str,
    rationale: str,
    capabilities: list[str],
    regimes: list[str],
    params: dict[str, Any],
) -> dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "hypothesis_id": strategy_id,
        "strategy_family": family,
        "strategy_version": "dev_v1",
        "economic_mechanism": mechanism,
        "component_id": component_id,
        "required_data_capabilities": capabilities,
        "eligible_symbol_profile": {
            "market_size_classes": ["MAINSTREAM", "MID_SIZE", "SMALL", "MEME"],
            "params": params,
        },
        "excluded_symbol_conditions": ["INSTRUMENT_METADATA_INVALID", "RESERVED_INTERVAL_OVERLAP"],
        "eligible_regimes": regimes,
        "excluded_regimes": ["CHAOS"],
        "context_timeframe": "60m",
        "event_timeframe": "15m",
        "entry_timeframe": "15m",
        "execution_resolution_timeframe": "15m",
        "context_definition": f"context_via_{component_id}",
        "event_definition": f"event_via_{component_id}",
        "confirmation_definition": "deterministic_confirmation_bar",
        "entry_definition": params.get("entry_definition", "next_open_after_confirm"),
        "late_entry_definition": "reject_if_extension_atr_gt_1.2",
        "stop_definition": params.get("stop_definition", "1.2_atr"),
        "target_definition": params.get("target_definition", "2.0_atr"),
        "exit_definition": "stop_or_target_or_max_hold",
        "maximum_holding_period": params.get("max_hold_bars", 48),
        "cost_buffer_definition": "taker_round_trip_plus_spread_slip",
        "spread_limit_definition": {"max_spread_bps": params.get("max_spread_bps", 8)},
        "slippage_limit_definition": {"max_slip_bps": params.get("max_slip_bps", 8)},
        "liquidity_requirement": {"min_turnover_usd": params.get("min_turnover", 1_000_000)},
        "risk_model_reference": "ISOLATED_25X_MARGIN_20_MAXLOSS_3",
        "position_size_model_reference": "FIXED_MARGIN_20_USDT",
        "development_interval_ids": [DEV_INTERVAL],
        "replay_interval_ids": [DEV_INTERVAL],
        "excluded_interval_ids": EXCLUDED,
        "parameter_source": "component_library_economic_prior_not_post_result",
        "economic_rationale": rationale,
        "preregistration_timestamp": "",
        "strategy_checksum": "",
        "semantic_checksum": "",
        "AI_provider_identities": {
            "proposal": "GROQ_MAIN_REASONER",
            "normalize": "CEREBRAS_RESEARCH_NORMALIZER",
            "critic": "SAMBANOVA_INDEPENDENT_CRITIC",
            "reflection": "GROQ_REFLECTION_REASONER",
        },
        "prompt_schema_versions": {
            "hypothesis_propose_v1": "hypothesis_propose_v1",
            "lesson_normalize_v1": "lesson_normalize_v1",
            "critic_v1": "critic_v1",
            "reflection_v1": "reflection_v1",
        },
        "development_window": {
            "start_ms": RESEARCH_V2_V3_START_MS,
            "end_ms": RESEARCH_V2_V3_END_MS,
        },
        "forbidden_windows": {
            "september_oos": [SEPTEMBER_OOS_START_MS, SEPTEMBER_OOS_END_MS],
        },
        "parameter_values": params,
    }


def default_hypothesis_drafts() -> list[dict[str, Any]]:
    """Deterministic economically distinct drafts — frozen before execution."""
    drafts = [
        _base(
            strategy_id="DEV_H01_TREND_CONTINUATION",
            family="TREND",
            component_id="TREND_CONTINUATION",
            mechanism="trend_pullback_continuation",
            rationale="Capture continuation after shallow pullback in established trend.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["TRENDING_UP", "TRENDING_DOWN"],
            params={"stop_definition": "1.0_atr", "target_definition": "2.2_atr", "cooldown_15m_bars": 24},
        ),
        _base(
            strategy_id="DEV_H02_STRUCTURAL_RETEST",
            family="STRUCTURE",
            component_id="STRUCTURAL_RETEST",
            mechanism="broken_level_retest",
            rationale="Enter on retest of recently broken structure with defined invalidation.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["TRENDING_UP", "TRENDING_DOWN", "RANGE"],
            params={"stop_definition": "beyond_structure", "target_definition": "1.8_r"},
        ),
        _base(
            strategy_id="DEV_H03_BREAKOUT",
            family="BREAKOUT",
            component_id="BREAKOUT",
            mechanism="range_break_with_volume",
            rationale="Break of compressed range with volume expansion; reject late extension.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["RANGE", "VOL_EXPAND"],
            params={"stop_definition": "range_mid", "target_definition": "range_height", "max_spread_bps": 6},
        ),
        _base(
            strategy_id="DEV_H04_FAILED_BREAKOUT",
            family="BREAKOUT",
            component_id="FAILED_BREAKOUT",
            mechanism="failed_break_reclaim",
            rationale="Fade failed breakouts that reclaim range interior quickly.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["RANGE", "VOL_EXPAND"],
            params={"stop_definition": "sweep_extreme", "target_definition": "range_mid"},
        ),
        _base(
            strategy_id="DEV_H05_MOMENTUM_ACCEL",
            family="MOMENTUM",
            component_id="MOMENTUM_ACCELERATION",
            mechanism="atr_acceleration_thrust",
            rationale="Enter when short-horizon momentum accelerates with liquidity.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["TRENDING_UP", "TRENDING_DOWN", "VOL_EXPAND"],
            params={"stop_definition": "1.3_atr", "target_definition": "2.5_atr"},
        ),
        _base(
            strategy_id="DEV_H06_VOL_EXPANSION",
            family="VOLATILITY",
            component_id="VOLATILITY_EXPANSION",
            mechanism="atr_percentile_expansion",
            rationale="Trade expansion from low-vol compression with adverse-first exits.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["VOL_EXPAND"],
            params={"stop_definition": "1.5_atr", "target_definition": "2.0_atr", "max_slip_bps": 10},
        ),
        _base(
            strategy_id="DEV_H07_VWAP_MR",
            family="MEAN_REVERSION",
            component_id="VWAP_MEAN_REVERSION",
            mechanism="vwap_deviation_revert",
            rationale="Fade stretched deviations from session VWAP in non-trend regimes.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["RANGE", "LOW_VOL"],
            params={"stop_definition": "1.0_atr", "target_definition": "vwap", "max_spread_bps": 5},
        ),
        _base(
            strategy_id="DEV_H08_STRUCT_MR",
            family="MEAN_REVERSION",
            component_id="STRUCTURAL_MEAN_REVERSION",
            mechanism="range_extreme_revert",
            rationale="Fade touches of established range extremes with tight invalidation.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["RANGE"],
            params={"stop_definition": "outside_range", "target_definition": "range_mid"},
        ),
        _base(
            strategy_id="DEV_H09_REL_STRENGTH",
            family="CROSS_SECTIONAL",
            component_id="RELATIVE_STRENGTH",
            mechanism="vs_btc_relative_strength",
            rationale="Prefer symbols showing strength/weakness versus BTC in trend regimes.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["TRENDING_UP", "TRENDING_DOWN"],
            params={"stop_definition": "1.2_atr", "target_definition": "2.0_atr"},
        ),
        _base(
            strategy_id="DEV_H10_XS_MOMENTUM",
            family="CROSS_SECTIONAL",
            component_id="CROSS_SECTIONAL_MOMENTUM",
            mechanism="cross_sectional_rank_momentum",
            rationale="Rank-based momentum bucket entries among research-eligible names.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["TRENDING_UP", "TRENDING_DOWN"],
            params={"stop_definition": "1.2_atr", "target_definition": "2.0_atr", "min_turnover": 2_000_000},
        ),
        _base(
            strategy_id="DEV_H11_FUNDING_OI_CONT",
            family="DERIVATIVES",
            component_id="FUNDING_OI_CONTINUATION",
            mechanism="funding_oi_aligned_continuation",
            rationale="Continue when funding and OI confirm directional pressure.",
            capabilities=["DERIVATIVES_HISTORY_ELIGIBLE", "PRICE_HISTORY_ELIGIBLE"],
            regimes=["TRENDING_UP", "TRENDING_DOWN"],
            params={"stop_definition": "1.2_atr", "target_definition": "2.0_atr"},
        ),
        _base(
            strategy_id="DEV_H12_LIQ_SWEEP",
            family="REVERSAL",
            component_id="LIQUIDITY_SWEEP_REVERSAL",
            mechanism="liquidity_sweep_reclaim",
            rationale="Enter after liquidity sweep and reclaim of prior structure.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["RANGE", "VOL_EXPAND"],
            params={"stop_definition": "sweep_extreme", "target_definition": "1.6_r"},
        ),
    ]
    assert len(drafts) <= MAX_DEVELOPMENT_HYPOTHESES
    families = {d["strategy_family"] for d in drafts}
    assert len(families) >= MIN_STRATEGY_FAMILIES
    for d in drafts:
        assert d["component_id"] in COMPONENT_IDS
    return drafts


def preregister_hypotheses(drafts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    drafts = drafts or default_hypothesis_drafts()
    if len(drafts) > MAX_DEVELOPMENT_HYPOTHESES:
        raise ValueError("max_12_hypotheses")
    frozen = [freeze_spec(d) for d in drafts]
    families = sorted({h["strategy_family"] for h in frozen})
    if len(families) < MIN_STRATEGY_FAMILIES:
        raise ValueError("min_four_families")
    # Ensure components exist
    reg = component_registry()
    ids = {c["component_id"] for c in reg["components"]}
    for h in frozen:
        if h["component_id"] not in ids:
            raise ValueError(f"unknown_component:{h['component_id']}")
    return {
        "schema": "ai_hypothesis_preregistration_v1",
        "created_before_execution": True,
        "post_result_hypothesis_insertion_forbidden": True,
        "max_hypotheses": MAX_DEVELOPMENT_HYPOTHESES,
        "generated_hypothesis_count": len(frozen),
        "preregistered_hypothesis_count": len(frozen),
        "strategy_family_count": len(families),
        "strategy_families": families,
        "hypotheses": frozen,
        "component_registry_ref": "strategy_component_registry_v1",
        "formal_walk_forward_forbidden_in_this_task": True,
        "oos_creation_forbidden": True,
        "demo_forbidden": True,
    }
