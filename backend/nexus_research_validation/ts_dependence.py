"""Time-series dependence controls (ACF / effective sample size)."""
from __future__ import annotations

import math
from typing import Any, Sequence

from backend.nexus_research_validation.constants import (
    ACF_DEPENDENCE_THRESHOLD,
    MAX_ACF_LAG,
    MIN_EFFECTIVE_SAMPLE_AFTER_DEPENDENCE,
)


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def autocorrelation(series: Sequence[float], lag: int) -> float:
    n = len(series)
    if n < lag + 2 or lag < 1:
        return 0.0
    mu = _mean(series)
    num = sum((series[i] - mu) * (series[i - lag] - mu) for i in range(lag, n))
    den = sum((x - mu) ** 2 for x in series)
    if den <= 1e-18:
        return 0.0
    return num / den


def acf_profile(
    series: Sequence[float],
    *,
    max_lag: int = MAX_ACF_LAG,
) -> dict[str, Any]:
    lags = list(range(1, max_lag + 1))
    acfs = [autocorrelation(series, lag) for lag in lags]
    max_abs = max((abs(a) for a in acfs), default=0.0)
    # First lag where |acf| drops below threshold, else max_lag
    decay_lag = max_lag
    for lag, a in zip(lags, acfs):
        if abs(a) < ACF_DEPENDENCE_THRESHOLD:
            decay_lag = lag
            break
    dependent = max_abs >= ACF_DEPENDENCE_THRESHOLD
    return {
        "max_lag": max_lag,
        "acf": [{"lag": lag, "acf": a} for lag, a in zip(lags, acfs)],
        "max_abs_acf": max_abs,
        "decay_lag": decay_lag,
        "dependence_flagged": dependent,
        "threshold": ACF_DEPENDENCE_THRESHOLD,
    }


def effective_sample_size(
    series: Sequence[float],
    *,
    max_lag: int = MAX_ACF_LAG,
) -> dict[str, Any]:
    """n_eff ≈ n / (1 + 2 Σ ρ_k) truncated for positive dependence."""
    n = len(series)
    if n == 0:
        return {
            "n": 0,
            "n_eff": 0.0,
            "sum_rho": 0.0,
            "sufficient": False,
            "min_required": MIN_EFFECTIVE_SAMPLE_AFTER_DEPENDENCE,
        }
    sum_rho = 0.0
    for lag in range(1, min(max_lag, n - 1) + 1):
        rho = autocorrelation(series, lag)
        if rho <= 0:
            break
        sum_rho += rho
    denom = 1.0 + 2.0 * sum_rho
    n_eff = n / denom if denom > 0 else float(n)
    n_eff = max(1.0, min(float(n), n_eff))
    return {
        "n": n,
        "n_eff": n_eff,
        "sum_rho": sum_rho,
        "sufficient": n_eff >= MIN_EFFECTIVE_SAMPLE_AFTER_DEPENDENCE,
        "min_required": MIN_EFFECTIVE_SAMPLE_AFTER_DEPENDENCE,
        "acf": acf_profile(series, max_lag=max_lag),
        "development_only": True,
    }


def ts_dependence_controls(series: Sequence[float]) -> dict[str, Any]:
    ess = effective_sample_size(series)
    return {
        "acf_profile": ess["acf"],
        "effective_sample_size": {
            "n": ess["n"],
            "n_eff": ess["n_eff"],
            "sum_rho": ess["sum_rho"],
            "sufficient": ess["sufficient"],
            "min_required": ess["min_required"],
        },
        "dependence_blocks_robust_claim": (
            ess["acf"]["dependence_flagged"] and not ess["sufficient"]
        ),
        "formal_walk_forward": False,
        "not_oos_claim": True,
    }
