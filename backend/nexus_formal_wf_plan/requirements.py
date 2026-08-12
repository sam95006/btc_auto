"""Failure thresholds, sample-size floors, regime/symbol requirements (plan-only)."""
from __future__ import annotations

from typing import Any

from backend.nexus_formal_wf_plan.constants import (
    DEFAULT_MIN_TRAIN_BARS,
    DEFAULT_MIN_VAL_BARS,
)


def build_failure_thresholds(candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    overrides = (candidate or {}).get("failure_thresholds") or {}
    return {
        "max_drawdown_pct": float(overrides.get("max_drawdown_pct", 25.0)),
        "max_cost_drag_pct": float(overrides.get("max_cost_drag_pct", 100.0)),
        "min_positive_fold_ratio": float(overrides.get("min_positive_fold_ratio", 0.5)),
        "max_regime_fragility_score": float(overrides.get("max_regime_fragility_score", 0.75)),
        "note": "Thresholds are planned gates only; no fold metrics are evaluated.",
        "evaluated": False,
        "executed": False,
    }


def build_minimum_sample_sizes(candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    overrides = (candidate or {}).get("minimum_sample_sizes") or {}
    return {
        "min_train_bars": int(overrides.get("min_train_bars", DEFAULT_MIN_TRAIN_BARS)),
        "min_validation_bars": int(overrides.get("min_validation_bars", DEFAULT_MIN_VAL_BARS)),
        "min_symbols_per_fold": int(overrides.get("min_symbols_per_fold", 1)),
        "min_regime_observations": int(overrides.get("min_regime_observations", 30)),
        "note": "Sample floors are plan constraints; sample counts are not measured here.",
        "measured": False,
        "executed": False,
    }


def build_regime_requirements(candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    overrides = (candidate or {}).get("regime_requirements") or {}
    required = list(
        overrides.get("required_regimes")
        or ["TRENDING", "MEAN_REVERTING", "HIGH_VOL", "LOW_VOL"]
    )
    return {
        "required_regimes": required,
        "min_regimes_covered": int(overrides.get("min_regimes_covered", max(2, len(required) // 2))),
        "allow_single_regime_claim": False,
        "note": "Regime coverage is a planned requirement; coverage is not computed here.",
        "evaluated": False,
        "executed": False,
    }


def build_symbol_requirements(candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    overrides = (candidate or {}).get("symbol_requirements") or {}
    symbols = list(
        overrides.get("required_symbols")
        or candidate.get("symbols")
        or ["BTCUSDT"]
    )
    return {
        "required_symbols": symbols,
        "min_symbols": int(overrides.get("min_symbols", 1)),
        "universe_category": "DEVELOPMENT",
        "oos_symbols_forbidden": True,
        "note": "Symbol requirements are planned; universe membership is not verified here.",
        "evaluated": False,
        "executed": False,
    }


def build_plan_requirements(candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "failure_thresholds": build_failure_thresholds(candidate),
        "minimum_sample_sizes": build_minimum_sample_sizes(candidate),
        "regime_requirements": build_regime_requirements(candidate),
        "symbol_requirements": build_symbol_requirements(candidate),
        "all_unevaluated": True,
        "formal_walk_forward_executed": False,
    }
