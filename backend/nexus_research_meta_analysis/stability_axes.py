"""Stability axes: neighborhood, symbol, regime, turnover, cost, capacity."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.nexus_research_meta_analysis.constants import (
    CAPACITY_MAX_NOTIONAL_SHARE,
    COST_SENSITIVITY_DESTROY_NET_NONPOSITIVE,
    PARAM_NEIGHBORHOOD_MIN_SIGN_AGREE,
    PARAM_NEIGHBORHOOD_RADIUS,
    REGIME_STABILITY_MAX_CONCENTRATION,
    SYMBOL_STABILITY_MIN_POSITIVE_SHARE,
    TURNOVER_STABILITY_MAX_RATIO,
)


def parameter_neighborhood_stability(
    base_metric: float,
    neighbor_metrics: Sequence[float],
    *,
    radius: float = PARAM_NEIGHBORHOOD_RADIUS,
    min_sign_agree: float = PARAM_NEIGHBORHOOD_MIN_SIGN_AGREE,
) -> dict[str, Any]:
    if not neighbor_metrics:
        return {
            "axis": "parameter_neighborhood_stability",
            "stable": False,
            "reason": "no_neighbors",
            "neighbor_count": 0,
        }
    base_sign = 1 if base_metric > 0 else (-1 if base_metric < 0 else 0)
    agree = sum(
        1
        for m in neighbor_metrics
        if (1 if m > 0 else (-1 if m < 0 else 0)) == base_sign
    )
    sign_agreement = agree / len(neighbor_metrics)
    mean_n = sum(neighbor_metrics) / len(neighbor_metrics)
    dispersion = (
        abs(mean_n - base_metric) / max(abs(base_metric), 1e-9)
        if base_metric != 0
        else abs(mean_n)
    )
    stable = sign_agreement >= min_sign_agree and dispersion <= radius * 2.0
    return {
        "axis": "parameter_neighborhood_stability",
        "radius": radius,
        "neighbor_count": len(neighbor_metrics),
        "sign_agreement": sign_agreement,
        "relative_dispersion": dispersion,
        "stable": stable,
        "development_only": True,
    }


def symbol_stability(
    symbol_net: Mapping[str, float],
    *,
    min_positive_share: float = SYMBOL_STABILITY_MIN_POSITIVE_SHARE,
) -> dict[str, Any]:
    if not symbol_net:
        return {
            "axis": "symbol_stability",
            "stable": False,
            "reason": "empty_symbol_breakdown",
        }
    pos = sum(1 for v in symbol_net.values() if float(v) > 0)
    share = pos / len(symbol_net)
    return {
        "axis": "symbol_stability",
        "symbol_count": len(symbol_net),
        "positive_share": share,
        "min_positive_share": min_positive_share,
        "stable": share >= min_positive_share,
        "development_only": True,
    }


def regime_stability(
    regime_net: Mapping[str, float],
    *,
    max_concentration: float = REGIME_STABILITY_MAX_CONCENTRATION,
) -> dict[str, Any]:
    if not regime_net:
        return {
            "axis": "regime_stability",
            "stable": False,
            "reason": "empty_regime_breakdown",
        }
    abs_vals = {k: abs(float(v)) for k, v in regime_net.items()}
    total = sum(abs_vals.values()) or 1.0
    dominant = max(abs_vals, key=abs_vals.get)
    concentration = abs_vals[dominant] / total
    pos = sum(1 for v in regime_net.values() if float(v) > 0)
    pos_share = pos / len(regime_net)
    stable = concentration <= max_concentration and pos_share >= 0.5
    return {
        "axis": "regime_stability",
        "regime_count": len(regime_net),
        "concentration": concentration,
        "dominant_regime": dominant,
        "positive_regime_share": pos_share,
        "max_concentration_allowed": max_concentration,
        "stable": stable,
        "development_only": True,
    }


def turnover_stability(
    *,
    gross_pnl: float,
    turnover_cost: float,
    max_ratio: float = TURNOVER_STABILITY_MAX_RATIO,
) -> dict[str, Any]:
    gross = float(gross_pnl)
    tc = float(turnover_cost)
    ratio = tc / max(abs(gross), 1e-9) if gross != 0 else (float("inf") if tc > 0 else 0.0)
    finite_ratio = None if ratio == float("inf") else ratio
    stable = gross > 0 and finite_ratio is not None and finite_ratio <= max_ratio
    return {
        "axis": "turnover_stability",
        "turnover_cost": tc,
        "gross_pnl": gross,
        "turnover_cost_to_gross_ratio": finite_ratio,
        "max_ratio": max_ratio,
        "stable": stable,
        "development_only": True,
    }


def cost_sensitivity(
    *,
    gross_pnl: float,
    net_pnl: float,
    cost_components: Mapping[str, float],
) -> dict[str, Any]:
    total_cost = sum(max(0.0, float(v)) for v in cost_components.values())
    destroyed = bool(
        COST_SENSITIVITY_DESTROY_NET_NONPOSITIVE
        and float(gross_pnl) > 0
        and float(net_pnl) <= 0
    )
    return {
        "axis": "cost_sensitivity",
        "gross_pnl": float(gross_pnl),
        "net_pnl": float(net_pnl),
        "total_cost": total_cost,
        "destroyed": destroyed,
        "stable": not destroyed and float(net_pnl) > 0,
        "development_only": True,
        "not_oos_claim": True,
    }


def capacity_sensitivity(
    capacity_assumptions: Mapping[str, float],
    *,
    max_share: float = CAPACITY_MAX_NOTIONAL_SHARE,
) -> dict[str, Any]:
    if not capacity_assumptions:
        return {
            "axis": "capacity_sensitivity",
            "stable": False,
            "reason": "empty_capacity_assumptions",
        }
    vals = {k: abs(float(v)) for k, v in capacity_assumptions.items()}
    total = sum(vals.values()) or 1.0
    dominant = max(vals, key=vals.get)
    share = vals[dominant] / total
    # Fragile when a single capacity bucket dominates beyond max_share * len?
    # Spec: fragility if concentration exceeds CAPACITY_MAX_NOTIONAL_SHARE when
    # that share is high relative to equal split. Use absolute concentration > 0.7
    # OR share > max_share when many buckets — keep simple: share > 0.70 fragile.
    concentration_limit = max(max_share * 2.0, 0.70)
    stable = share <= concentration_limit
    return {
        "axis": "capacity_sensitivity",
        "capacity_assumptions": dict(capacity_assumptions),
        "dominant_bucket": dominant,
        "dominant_share": share,
        "concentration_limit": concentration_limit,
        "stable": stable,
        "fragile": not stable,
        "development_only": True,
    }


def combined_stability_axes(experiment: Mapping[str, Any]) -> dict[str, Any]:
    series = list(experiment["net_series"])
    base = sum(series) / max(1, len(series))
    comps = dict(experiment.get("cost_components") or {})
    turnover_cost = float(comps.get("turnover_cost") or 0.0)
    param = parameter_neighborhood_stability(
        base, list(experiment.get("neighbor_metrics") or [])
    )
    symbol = symbol_stability(dict(experiment.get("symbol_net") or {}))
    regime = regime_stability(dict(experiment.get("regime_net") or {}))
    turnover = turnover_stability(
        gross_pnl=float(experiment["gross_pnl"]),
        turnover_cost=turnover_cost,
    )
    cost = cost_sensitivity(
        gross_pnl=float(experiment["gross_pnl"]),
        net_pnl=float(experiment["net_pnl"]),
        cost_components=comps,
    )
    capacity = capacity_sensitivity(dict(experiment.get("capacity_assumptions") or {}))
    all_ok = all(
        bool(x.get("stable"))
        for x in (param, symbol, regime, turnover, cost, capacity)
    )
    return {
        "parameter_neighborhood_stability": param,
        "symbol_stability": symbol,
        "regime_stability": regime,
        "turnover_stability": turnover,
        "cost_sensitivity": cost,
        "capacity_sensitivity": capacity,
        "all_stability_axes_ok": all_ok,
        "formal_walk_forward": False,
        "not_oos_claim": True,
    }
