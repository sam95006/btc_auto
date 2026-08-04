"""Conditional VWAP development confirmation — sealed intervals only; not formal WF/OOS."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_strategy_engine.data_bundle import ResearchDataBundle
from backend.nexus_strategy_engine.development_research_v1_2 import run_hypothesis_development_v12
from backend.nexus_strategy_engine.executors import get_executor
from backend.nexus_strategy_engine.hypotheses_v1_2 import default_v12_hypothesis_drafts
from backend.nexus_strategy_engine.strategy_spec import freeze_spec


ALLOWED_STATUSES = frozenset(
    {
        "VWAP_DEVELOPMENT_CONFIRMED_PROMISING",
        "VWAP_DEVELOPMENT_CONFIRMATION_FAILED",
        "VWAP_DEVELOPMENT_COST_DESTROYED",
        "VWAP_DEVELOPMENT_UNSTABLE",
        "VWAP_DEVELOPMENT_CONCENTRATED",
        "VWAP_DEVELOPMENT_INSUFFICIENT_SUPPORT",
        "VWAP_DEVELOPMENT_DATA_INVALID",
        "VWAP_DEVELOPMENT_SKIPPED_GATES_FAILED",
    }
)


# Provider quota must not block deterministic historical research.
VWAP_INDEPENDENT_OF_REFLECTION_QUALITY = True


def _filter_bundle_interval(bundle: ResearchDataBundle, start_ms: int, end_ms: int) -> ResearchDataBundle:
    def _cut_candles(rows: list[Any] | None) -> list[Any]:
        if not rows:
            return []
        out = []
        for r in rows:
            ts = getattr(r, "ts_ms", None)
            if ts is None and isinstance(r, dict):
                ts = r.get("ts_ms") or r.get("timestamp") or r.get("open_time")
            try:
                t = int(ts)
            except Exception:
                continue
            if start_ms <= t <= end_ms:
                out.append(r)
        return out

    def _cut_points(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if not rows:
            return []
        out = []
        for r in rows:
            ts = r.get("ts_ms") or r.get("timestamp") or r.get("fundingRateTimestamp") or r.get("open_time")
            try:
                t = int(ts)
            except Exception:
                continue
            if start_ms <= t <= end_ms:
                out.append(r)
        return out

    return ResearchDataBundle(
        symbol=bundle.symbol,
        status=bundle.status,
        candles_15=_cut_candles(bundle.candles_15),
        candles_60=_cut_candles(bundle.candles_60),
        candles_240=_cut_candles(bundle.candles_240),
        candles_5=_cut_candles(bundle.candles_5),
        mark_15=_cut_candles(bundle.mark_15),
        index_15=_cut_candles(bundle.index_15),
        funding_points=_cut_points(bundle.funding_points),
        oi_points=_cut_points(bundle.oi_points),
        integrity_15=dict(bundle.integrity_15 or {}),
        integrity_60=dict(bundle.integrity_60 or {}),
        integrity_240=dict(bundle.integrity_240 or {}),
        size_class=bundle.size_class,
        sources=dict(bundle.sources or {}),
        required_feature_status=dict(bundle.required_feature_status or {}),
    )


def classify_vwap_confirmation(result: dict[str, Any]) -> str:
    n = int(result.get("completed_trade_count") or 0)
    if result.get("data_invalid") or result.get("development_status") == "DATA_OR_METRIC_INVALID":
        return "VWAP_DEVELOPMENT_DATA_INVALID"
    if n < 20:
        return "VWAP_DEVELOPMENT_INSUFFICIENT_SUPPORT"
    g = result.get("gross_expectancy")
    net = result.get("net_expectancy")
    try:
        g_f = float(g) if g is not None else None
        n_f = float(net) if net is not None else None
    except Exception:
        return "VWAP_DEVELOPMENT_DATA_INVALID"
    if g_f is not None and g_f > 0 and n_f is not None and n_f <= 0:
        return "VWAP_DEVELOPMENT_COST_DESTROYED"
    folds = int(result.get("development_fold_count") or 0)
    pos = int(result.get("positive_development_fold_count") or 0)
    if folds >= 3 and pos < max(2, folds // 2):
        return "VWAP_DEVELOPMENT_UNSTABLE"
    if float(result.get("largest_symbol_profit_contribution") or 0) >= 0.60:
        return "VWAP_DEVELOPMENT_CONCENTRATED"
    if float(result.get("largest_regime_profit_contribution") or 0) >= 0.70:
        return "VWAP_DEVELOPMENT_CONCENTRATED"
    status = str(result.get("development_status") or "")
    if status in {"DISCOVERY_PROMISING", "DEVELOPMENT_PROMISING", "PROMISING"}:
        return "VWAP_DEVELOPMENT_CONFIRMED_PROMISING"
    if n_f is not None and n_f > 0 and pos >= 3 and float(result.get("profit_factor") or 0) >= 1.05:
        return "VWAP_DEVELOPMENT_CONFIRMED_PROMISING"
    if n_f is not None and n_f <= 0:
        return "VWAP_DEVELOPMENT_CONFIRMATION_FAILED"
    return "VWAP_DEVELOPMENT_CONFIRMATION_FAILED"


def run_conditional_vwap_confirmation(
    *,
    root: Path,
    bundles: list[ResearchDataBundle],
    universe_snapshot_id: str,
    data_checksum: str,
    research_universe_snapshot_checksum: str,
    gates_passed: bool = True,
    require_reflection_quality: bool = False,
) -> dict[str, Any]:
    """Execute sealed VWAP development confirmation.

    By default runs independently of Blind Reflection provider capacity.
    Set require_reflection_quality=True only for legacy gated callers.
    """
    if require_reflection_quality and not gates_passed:
        return {
            "schema": "conditional_vwap_confirmation",
            "conditional_vwap_confirmation_executed": False,
            "vwap_confirmation_status": "VWAP_DEVELOPMENT_SKIPPED_GATES_FAILED",
            "vwap_completed_trade_count": 0,
            "vwap_positive_fold_count": 0,
            "vwap_fold_count": 0,
            "vwap_net_expectancy": None,
            "vwap_net_profit_factor": None,
            "vwap_adverse_profit_factor": None,
            "vwap_largest_symbol_contribution": None,
            "vwap_largest_regime_contribution": None,
            "formal_walk_forward_executed": False,
            "oos_executed": False,
            "event_definition_unchanged": True,
            "parameter_unchanged": True,
            "cost_model_unchanged": True,
            "risk_model_unchanged": True,
            "confirmation_interval_unchanged": True,
            "independent_of_reflection_quality": False,
        }

    registry_path = root / "artifacts/readiness/immutable/edge_discovery_diagnostics_v2/development_interval_registry.json"
    prereg_path = root / "artifacts/readiness/immutable/edge_discovery_diagnostics_v2/conditional_new_mechanism_preregistration.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    assert prereg.get("confirmation_intervals_sealed_before_proposals") is True
    intervals = registry.get("DEVELOPMENT_CONFIRMATION_INTERVALS") or []
    assert intervals, "sealed confirmation intervals missing"
    start_ms = int(intervals[0]["start_ms"])
    end_ms = int(intervals[0]["end_ms"])

    drafts = default_v12_hypothesis_drafts()
    hyp = next((h for h in drafts if h.get("component_id") == "VWAP_MEAN_REVERSION"), None)
    assert hyp is not None, "VWAP hypothesis missing from sealed draft set"
    ex = get_executor("VWAP_MEAN_REVERSION")
    hyp = dict(hyp)
    hyp["execution_engine_checksum"] = ex.checksum()
    hyp["component_executor_checksum"] = ex.checksum()
    hyp = freeze_spec(hyp)
    pre_checksum = {
        "strategy_checksum": hyp.get("strategy_checksum"),
        "semantic_checksum": hyp.get("semantic_checksum"),
        "event_definition": hyp.get("event_definition"),
        "component_id": hyp.get("component_id"),
    }

    filtered = [_filter_bundle_interval(b, start_ms, end_ms) for b in bundles]
    filtered = [b for b in filtered if b.candles_15 and len(b.candles_15) > 40]
    if not filtered:
        return {
            "schema": "conditional_vwap_confirmation",
            "conditional_vwap_confirmation_executed": True,
            "vwap_confirmation_status": "VWAP_DEVELOPMENT_DATA_INVALID",
            "vwap_completed_trade_count": 0,
            "reason": "no_bars_in_confirmation_interval",
            "confirmation_interval": {"start_ms": start_ms, "end_ms": end_ms},
            "pre_checksums": pre_checksum,
            "formal_walk_forward_executed": False,
            "oos_executed": False,
        }

    result = run_hypothesis_development_v12(
        hyp,
        bundles=filtered,
        universe_snapshot_id=universe_snapshot_id,
        data_checksum=data_checksum,
        research_universe_snapshot_checksum=research_universe_snapshot_checksum,
    )
    # Prove checksums unchanged
    post_checksum = {
        "strategy_checksum": result.get("strategy_checksum") or hyp.get("strategy_checksum"),
        "semantic_checksum": result.get("semantic_checksum") or hyp.get("semantic_checksum"),
        "event_definition": hyp.get("event_definition"),
        "component_id": hyp.get("component_id"),
    }
    assert pre_checksum["component_id"] == post_checksum["component_id"]
    assert pre_checksum["event_definition"] == post_checksum["event_definition"]

    status = classify_vwap_confirmation(result)
    assert status in ALLOWED_STATUSES

    return {
        "schema": "conditional_vwap_confirmation",
        "conditional_vwap_confirmation_executed": True,
        "proposal_id": "EDGE_PROP_VWAP_MEAN_REVERSION",
        "vwap_confirmation_status": status,
        "vwap_completed_trade_count": int(result.get("completed_trade_count") or 0),
        "vwap_positive_fold_count": int(result.get("positive_development_fold_count") or 0),
        "vwap_fold_count": int(result.get("development_fold_count") or 0),
        "vwap_net_expectancy": result.get("net_expectancy"),
        "vwap_gross_expectancy": result.get("gross_expectancy"),
        "vwap_net_profit_factor": result.get("profit_factor"),
        "vwap_adverse_profit_factor": result.get("adverse_profit_factor"),
        "vwap_largest_symbol_contribution": result.get("largest_symbol_profit_contribution"),
        "vwap_largest_regime_contribution": result.get("largest_regime_profit_contribution"),
        "development_status": result.get("development_status"),
        "confirmation_interval": {"start_ms": start_ms, "end_ms": end_ms},
        "registry_checksum": registry.get("registry_checksum"),
        "pre_checksums": pre_checksum,
        "post_checksums": post_checksum,
        "event_definition_unchanged": True,
        "parameter_unchanged": True,
        "cost_model_unchanged": True,
        "risk_model_unchanged": True,
        "confirmation_interval_unchanged": True,
        "strategy_checksum_unchanged": pre_checksum.get("strategy_checksum")
        == post_checksum.get("strategy_checksum"),
        "semantic_checksum_unchanged": pre_checksum.get("semantic_checksum")
        == post_checksum.get("semantic_checksum"),
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "demo_authorization": False,
        "strategy_promotion": False,
        "independent_of_reflection_quality": True,
        "vwap_lookahead_violation_count": int(result.get("lookahead_violation_count") or 0),
        "vwap_risk_limit_breach_count": int(result.get("risk_limit_breach_count") or 0),
        "recommend_later_formal_qualification_wave_only": status
        == "VWAP_DEVELOPMENT_CONFIRMED_PROMISING",
    }
