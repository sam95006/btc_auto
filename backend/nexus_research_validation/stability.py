"""Parameter-neighborhood, regime, and symbol stability probes."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.nexus_research_validation.constants import (
    PARAM_NEIGHBORHOOD_MIN_SIGN_AGREE,
    PARAM_NEIGHBORHOOD_RADIUS,
    REGIME_STABILITY_MIN_SHARE,
    SYMBOL_STABILITY_MIN_SHARE,
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
            "radius": radius,
            "neighbor_count": 0,
            "sign_agreement": 0.0,
            "relative_dispersion": None,
            "stable": False,
            "reason": "no_neighbors",
        }
    base_sign = 1 if base_metric > 0 else (-1 if base_metric < 0 else 0)
    agree = 0
    for m in neighbor_metrics:
        s = 1 if m > 0 else (-1 if m < 0 else 0)
        if s == base_sign:
            agree += 1
    sign_agreement = agree / len(neighbor_metrics)
    mean_n = sum(neighbor_metrics) / len(neighbor_metrics)
    dispersion = (
        abs(mean_n - base_metric) / max(abs(base_metric), 1e-9)
        if base_metric != 0
        else abs(mean_n)
    )
    stable = sign_agreement >= min_sign_agree and dispersion <= radius * 2.0
    return {
        "radius": radius,
        "neighbor_count": len(neighbor_metrics),
        "neighbor_metrics": list(neighbor_metrics),
        "base_metric": base_metric,
        "sign_agreement": sign_agreement,
        "relative_dispersion": dispersion,
        "stable": stable,
        "development_only": True,
    }


def regime_stability(
    regime_net: Mapping[str, float],
    *,
    max_concentration: float = REGIME_STABILITY_MIN_SHARE,
) -> dict[str, Any]:
    """Flag fragility when net edge concentrates in a single regime."""
    if not regime_net:
        return {
            "regime_count": 0,
            "concentration": 1.0,
            "dominant_regime": None,
            "positive_regime_share": 0.0,
            "stable": False,
            "reason": "empty_regime_breakdown",
        }
    abs_vals = {k: abs(float(v)) for k, v in regime_net.items()}
    total = sum(abs_vals.values()) or 1.0
    dominant = max(abs_vals, key=abs_vals.get)
    concentration = abs_vals[dominant] / total
    pos = sum(1 for v in regime_net.values() if float(v) > 0)
    pos_share = pos / len(regime_net)
    # Stable if not overly concentrated AND multiple regimes contribute positively
    stable = concentration <= max_concentration and pos_share >= 0.5
    return {
        "regime_count": len(regime_net),
        "regime_net": dict(regime_net),
        "concentration": concentration,
        "dominant_regime": dominant,
        "positive_regime_share": pos_share,
        "max_concentration_allowed": max_concentration,
        "stable": stable,
        "development_only": True,
    }


def symbol_stability(
    symbol_net: Mapping[str, float],
    *,
    min_positive_share: float = SYMBOL_STABILITY_MIN_SHARE,
) -> dict[str, Any]:
    if not symbol_net:
        return {
            "symbol_count": 0,
            "positive_share": 0.0,
            "stable": False,
            "reason": "empty_symbol_breakdown",
        }
    pos = sum(1 for v in symbol_net.values() if float(v) > 0)
    share = pos / len(symbol_net)
    return {
        "symbol_count": len(symbol_net),
        "symbol_net": dict(symbol_net),
        "positive_share": share,
        "min_positive_share": min_positive_share,
        "stable": share >= min_positive_share,
        "development_only": True,
    }


def combined_stability_report(
    *,
    base_metric: float,
    neighbor_metrics: Sequence[float],
    regime_net: Mapping[str, float],
    symbol_net: Mapping[str, float],
) -> dict[str, Any]:
    param = parameter_neighborhood_stability(base_metric, neighbor_metrics)
    regime = regime_stability(regime_net)
    symbol = symbol_stability(symbol_net)
    all_stable = bool(param["stable"] and regime["stable"] and symbol["stable"])
    return {
        "parameter_neighborhood": param,
        "regime": regime,
        "symbol": symbol,
        "all_stability_axes_ok": all_stable,
        "formal_walk_forward": False,
        "not_oos_claim": True,
    }
