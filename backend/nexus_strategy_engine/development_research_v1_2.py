"""V1.2 development research — broad coverage; same discovery gates; no WF/OOS."""
from __future__ import annotations

from typing import Any

from backend.nexus_strategy_engine.data_bundle import ResearchDataBundle
from backend.nexus_strategy_engine.development_research_v1_1 import (
    build_candidates_for_component,
    classify_discovery_v11,
    empty_funnel,
    recommend_future_candidates_v11,
    run_hypothesis_development_v11,
)
from backend.nexus_strategy_engine.executors import get_executor
from backend.nexus_strategy_engine.strategy_spec import validate_spec

MIN_CROSS_SECTIONAL_UNIVERSE = 20
CROSS_SECTIONAL_TOO_SMALL = "CROSS_SECTIONAL_UNIVERSE_TOO_SMALL"


def recommend_future_candidates_v12(results: list[dict[str, Any]], *, max_n: int = 3) -> list[dict[str, Any]]:
    return recommend_future_candidates_v11(results, max_n=max_n)


def run_hypothesis_development_v12(
    hyp: dict[str, Any],
    *,
    bundles: list[ResearchDataBundle],
    universe_snapshot_id: str,
    data_checksum: str,
    research_universe_snapshot_checksum: str,
) -> dict[str, Any]:
    component_id = str(hyp.get("component_id") or "")
    # Cross-sectional minimum universe — not a cost-gate failure
    if component_id in {"RELATIVE_STRENGTH", "CROSS_SECTIONAL_MOMENTUM"}:
        eligible = sum(
            1
            for b in bundles
            if b.candles_15
            and len(b.candles_15) > 40
            and b.status
            in {
                "PRICE_MULTI_TIMEFRAME_READY",
                "DERIVATIVES_MULTI_TIMEFRAME_READY",
                "PRICE_ONLY_READY",
            }
        )
        if eligible < MIN_CROSS_SECTIONAL_UNIVERSE:
            funnel = empty_funnel()
            funnel["data_capability_block_count"] = 1
            ex = get_executor(component_id)
            return {
                "hypothesis_id": hyp.get("strategy_id"),
                "component_executor_id": component_id,
                "strategy_family": hyp.get("strategy_family"),
                "development_status": "DISCOVERY_INSUFFICIENT_SAMPLE",
                "zero_trade_root_cause": CROSS_SECTIONAL_TOO_SMALL,
                "cross_sectional_block": CROSS_SECTIONAL_TOO_SMALL,
                "eligible_ranking_symbol_count": eligible,
                "eligible_symbol_count": eligible,
                "completed_trade_count": 0,
                "candidate_funnel": funnel,
                "candidate_count": 0,
                "development_fold_count": 0,
                "positive_development_fold_count": 0,
                "net_expectancy": None,
                "profit_factor": None,
                "adverse_profit_factor": None,
                "maximum_drawdown": None,
                "largest_fold_profit_contribution": 0.0,
                "largest_symbol_profit_contribution": 0.0,
                "largest_regime_profit_contribution": 0.0,
                "semantic_execution_collision": False,
                "required_data_proxy_violation_count": 0,
                "lookahead_violation_count": 0,
                "risk_limit_breach_count": 0,
                "strategy_checksum": hyp.get("strategy_checksum"),
                "semantic_checksum": hyp.get("semantic_checksum"),
                "execution_engine_checksum": hyp.get("execution_engine_checksum") or ex.checksum(),
                "component_executor_checksum": hyp.get("component_executor_checksum") or ex.checksum(),
                "research_universe_snapshot_checksum": research_universe_snapshot_checksum,
                "data_bundle_checksum": data_checksum,
                "formal_walk_forward_executed": False,
                "oos_reservation_created": False,
                "not_cost_gate_failure": True,
            }

    result = run_hypothesis_development_v11(
        hyp,
        bundles=bundles,
        universe_snapshot_id=universe_snapshot_id,
        data_checksum=data_checksum,
    )
    result["research_universe_snapshot_checksum"] = research_universe_snapshot_checksum
    result["data_bundle_checksum"] = data_checksum
    result["component_executor_checksum"] = hyp.get("component_executor_checksum") or result.get(
        "execution_engine_checksum"
    )
    # Enrich ranking evidence for XS components when trades exist
    if component_id in {"RELATIVE_STRENGTH", "CROSS_SECTIONAL_MOMENTUM"}:
        eligible = sum(1 for b in bundles if b.candles_15 and len(b.candles_15) > 40)
        result["eligible_ranking_symbol_count"] = eligible
        result["ranking_evidence_required"] = [
            "ranking_timestamp",
            "point_in_time_membership_snapshot",
            "eligible_ranking_symbols",
            "benchmark",
            "ranking_feature",
            "rank_percentile",
            "long_bucket",
            "short_bucket",
            "rebalance_rule",
        ]
        if eligible < MIN_CROSS_SECTIONAL_UNIVERSE and int(result.get("completed_trade_count") or 0) == 0:
            result["zero_trade_root_cause"] = CROSS_SECTIONAL_TOO_SMALL
            result["not_cost_gate_failure"] = True
    return result


# re-export for runners
__all__ = [
    "run_hypothesis_development_v12",
    "recommend_future_candidates_v12",
    "classify_discovery_v11",
    "build_candidates_for_component",
    "CROSS_SECTIONAL_TOO_SMALL",
    "MIN_CROSS_SECTIONAL_UNIVERSE",
]
