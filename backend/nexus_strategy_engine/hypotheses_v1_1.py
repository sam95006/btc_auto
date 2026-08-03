"""V1.1 preregistration — does NOT mutate original V1 twelve hypotheses."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_demo_execution.closed_historical_registry import (
    RESEARCH_V2_V3_END_MS,
    RESEARCH_V2_V3_START_MS,
    SEPTEMBER_OOS_END_MS,
    SEPTEMBER_OOS_START_MS,
)
from backend.nexus_strategy_engine.components import COMPONENT_IDS
from backend.nexus_strategy_engine.constants import MAX_DEVELOPMENT_HYPOTHESES, MIN_STRATEGY_FAMILIES
from backend.nexus_strategy_engine.cost_semantics import COST_MODEL_VERSION
from backend.nexus_strategy_engine.data_bundle import DATA_BUNDLE_VERSION
from backend.nexus_strategy_engine.executors import get_executor
from backend.nexus_strategy_engine.strategy_spec import freeze_spec

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
    ex = get_executor(component_id)
    return {
        "strategy_id": strategy_id,
        "hypothesis_id": strategy_id,
        "strategy_family": family,
        "strategy_version": "dev_v1_1",
        "economic_mechanism": mechanism,
        "component_id": component_id,
        "component_executor_id": component_id,
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
        "context_definition": f"v11_context_{component_id}",
        "event_definition": f"v11_event_{component_id}",
        "confirmation_definition": f"v11_confirm_{component_id}",
        "entry_definition": params.get("entry_definition", "close_of_signal_bar"),
        "late_entry_definition": params.get("late_entry_definition", "component_specific"),
        "stop_definition": params.get("stop_definition", "component_specific"),
        "target_definition": params.get("target_definition", "component_specific"),
        "exit_definition": "component_stop_or_target_or_max_hold",
        "maximum_holding_period": params.get("max_hold_bars", 48),
        "cost_buffer_definition": "taker_round_trip_plus_conservative_proxy",
        "spread_limit_definition": {"max_spread_bps": params.get("max_spread_bps", 8)},
        "slippage_limit_definition": {"max_slip_bps": params.get("max_slip_bps", 8)},
        "liquidity_requirement": {"min_turnover_usd": params.get("min_turnover", 1_000_000)},
        "risk_model_reference": "ISOLATED_25X_MARGIN_20_MAXLOSS_3",
        "position_size_model_reference": "FIXED_MARGIN_20_USDT",
        "development_interval_ids": ["DEV_RESEARCH_V2_V3_SPAN"],
        "replay_interval_ids": ["DEV_RESEARCH_V2_V3_SPAN"],
        "excluded_interval_ids": EXCLUDED,
        "parameter_source": "component_executor_economic_prior_not_post_result",
        "economic_rationale": rationale,
        "preregistration_timestamp": "",
        "strategy_checksum": "",
        "semantic_checksum": "",
        "execution_engine_checksum": ex.checksum(),
        "data_bundle_version": DATA_BUNDLE_VERSION,
        "cost_model_version": COST_MODEL_VERSION,
        "component_executor_checksum": ex.checksum(),
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
            "reflection_v1": "reflection_v2_1",
        },
        "development_window": {
            "start_ms": RESEARCH_V2_V3_START_MS,
            "end_ms": RESEARCH_V2_V3_END_MS,
        },
        "forbidden_windows": {
            "september_oos": [SEPTEMBER_OOS_START_MS, SEPTEMBER_OOS_END_MS],
        },
        "parameter_values": params,
        "v1_preregistration_mutated": False,
    }


def default_v11_hypothesis_drafts() -> list[dict[str, Any]]:
    """At most 12; at least 6 genuinely distinct implemented components."""
    drafts = [
        _base(
            strategy_id="V11_H01_TREND_CONTINUATION",
            family="TREND",
            component_id="TREND_CONTINUATION",
            mechanism="trend_pullback_continuation_mtf",
            rationale="60m slope context + 15m pullback resume; structure invalidation.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["TRENDING_UP", "TRENDING_DOWN"],
            params={
                "stop_definition": "pullback_swing_invalidation",
                "target_definition": "atr_continuation_2_5",
                "late_entry_definition": "reject_if_ext_gt_1_5_atr_from_60m",
            },
        ),
        _base(
            strategy_id="V11_H02_STRUCTURAL_RETEST",
            family="STRUCTURE",
            component_id="STRUCTURAL_RETEST",
            mechanism="broken_level_retest",
            rationale="Retest of broken structure with measured-move target.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["TRENDING_UP", "TRENDING_DOWN", "RANGE"],
            params={"stop_definition": "broken_level_invalidation", "target_definition": "measured_range_height"},
        ),
        _base(
            strategy_id="V11_H03_BREAKOUT",
            family="BREAKOUT",
            component_id="BREAKOUT",
            mechanism="range_break_volume",
            rationale="Range break with volume; range re-entry invalidation.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["RANGE", "VOL_EXPAND"],
            params={"stop_definition": "range_reentry_invalidation", "target_definition": "measured_move_range_height"},
        ),
        _base(
            strategy_id="V11_H04_FAILED_BREAKOUT",
            family="BREAKOUT",
            component_id="FAILED_BREAKOUT",
            mechanism="failed_break_reclaim",
            rationale="Fade failed extremes to range midpoint.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["RANGE", "VOL_EXPAND"],
            params={"stop_definition": "failed_extreme_invalidation", "target_definition": "range_midpoint"},
        ),
        _base(
            strategy_id="V11_H05_MOMENTUM_ACCEL",
            family="MOMENTUM",
            component_id="MOMENTUM_ACCELERATION",
            mechanism="atr_acceleration_thrust",
            rationale="ATR acceleration with directional thrust.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["TRENDING_UP", "TRENDING_DOWN", "VOL_EXPAND"],
            params={"stop_definition": "atr_thrust_invalidation_1_0", "target_definition": "atr_thrust_target_2_8"},
        ),
        _base(
            strategy_id="V11_H06_VOL_EXPANSION",
            family="VOLATILITY",
            component_id="VOLATILITY_EXPANSION",
            mechanism="compression_to_expansion",
            rationale="ATR percentile expansion after compression.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["VOL_EXPAND"],
            params={"stop_definition": "atr_percentile_invalidation_1_6", "target_definition": "vol_expansion_target_2_2"},
        ),
        _base(
            strategy_id="V11_H07_VWAP_MR",
            family="MEAN_REVERSION",
            component_id="VWAP_MEAN_REVERSION",
            mechanism="vwap_deviation_revert",
            rationale="Fade VWAP stretch in non-trend 60m regimes.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["RANGE", "LOW_VOL"],
            params={"stop_definition": "extension_invalidation_1_0atr", "target_definition": "vwap_mean", "max_spread_bps": 5},
        ),
        _base(
            strategy_id="V11_H08_STRUCT_MR",
            family="MEAN_REVERSION",
            component_id="STRUCTURAL_MEAN_REVERSION",
            mechanism="range_extreme_revert",
            rationale="Fade range extremes to structural mid.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["RANGE"],
            params={"stop_definition": "outside_range_invalidation", "target_definition": "structural_range_mid"},
        ),
        _base(
            strategy_id="V11_H09_REL_STRENGTH",
            family="CROSS_SECTIONAL",
            component_id="RELATIVE_STRENGTH",
            mechanism="cross_sectional_rs_vs_btc",
            rationale="Point-in-time cross-sectional ranking vs BTC benchmark.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["TRENDING_UP", "TRENDING_DOWN"],
            params={"stop_definition": "rs_atr_invalidation", "target_definition": "rs_atr_target"},
        ),
        _base(
            strategy_id="V11_H10_XS_MOMENTUM",
            family="CROSS_SECTIONAL",
            component_id="CROSS_SECTIONAL_MOMENTUM",
            mechanism="cross_sectional_rank_momentum",
            rationale="Cross-sectional momentum buckets with survivorship protection.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["TRENDING_UP", "TRENDING_DOWN"],
            params={"stop_definition": "xs_mom_invalidation", "target_definition": "xs_mom_target", "min_turnover": 2_000_000},
        ),
        _base(
            strategy_id="V11_H11_FUNDING_OI_CONT",
            family="DERIVATIVES",
            component_id="FUNDING_OI_CONTINUATION",
            mechanism="funding_oi_aligned_continuation",
            rationale="Requires actual Funding+OI — never price proxy.",
            capabilities=["DERIVATIVES_HISTORY_ELIGIBLE", "PRICE_HISTORY_ELIGIBLE"],
            regimes=["TRENDING_UP", "TRENDING_DOWN"],
            params={"stop_definition": "price_structure_plus_derivative_context", "target_definition": "funding_oi_continuation_target"},
        ),
        _base(
            strategy_id="V11_H12_LIQ_SWEEP",
            family="REVERSAL",
            component_id="LIQUIDITY_SWEEP_REVERSAL",
            mechanism="liquidity_sweep_reclaim",
            rationale="Sweep extreme invalidation + opposite liquidity target.",
            capabilities=["PRICE_HISTORY_ELIGIBLE"],
            regimes=["RANGE", "VOL_EXPAND"],
            params={"stop_definition": "sweep_extreme_invalidation", "target_definition": "opposite_liquidity"},
        ),
    ]
    assert len(drafts) <= MAX_DEVELOPMENT_HYPOTHESES
    families = {d["strategy_family"] for d in drafts}
    assert len(families) >= MIN_STRATEGY_FAMILIES
    comps = {d["component_id"] for d in drafts}
    assert len(comps) >= 6
    for d in drafts:
        assert d["component_id"] in COMPONENT_IDS
        assert get_executor(d["component_id"]).implemented
    return drafts


def preregister_v11_hypotheses(drafts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    drafts = drafts or default_v11_hypothesis_drafts()
    # Skip NOT_IMPLEMENTED
    runnable = [d for d in drafts if get_executor(d["component_id"]).implemented]
    frozen = []
    for d in runnable:
        # Stamp executor/data/cost identity BEFORE freeze so strategy_checksum validates
        ex = get_executor(d["component_id"])
        d = deepcopy(d)
        d["execution_engine_checksum"] = ex.checksum()
        d["component_executor_checksum"] = ex.checksum()
        d["data_bundle_version"] = DATA_BUNDLE_VERSION
        d["cost_model_version"] = COST_MODEL_VERSION
        # Fold executor identity into economic rationale fingerprint via parameter_values
        params = dict(d.get("parameter_values") or {})
        params["execution_engine_checksum"] = ex.checksum()
        params["data_bundle_version"] = DATA_BUNDLE_VERSION
        params["cost_model_version"] = COST_MODEL_VERSION
        d["parameter_values"] = params
        if isinstance(d.get("eligible_symbol_profile"), dict):
            d["eligible_symbol_profile"] = {
                **d["eligible_symbol_profile"],
                "params": params,
            }
        f = freeze_spec(d)
        frozen.append(f)
    families = sorted({h["strategy_family"] for h in frozen})
    return {
        "schema": "ai_hypothesis_preregistration_v1_1",
        "package": "STRATEGY_ENGINE_V1_1",
        "created_before_execution": True,
        "post_result_hypothesis_insertion_forbidden": True,
        "v1_twelve_mutated": False,
        "max_hypotheses": MAX_DEVELOPMENT_HYPOTHESES,
        "generated_hypothesis_count": len(drafts),
        "preregistered_hypothesis_count": len(frozen),
        "strategy_family_count": len(families),
        "strategy_families": families,
        "distinct_component_count": len({h["component_id"] for h in frozen}),
        "hypotheses": frozen,
        "formal_walk_forward_forbidden_in_this_task": True,
        "oos_creation_forbidden": True,
        "demo_forbidden": True,
    }
