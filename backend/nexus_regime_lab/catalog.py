"""Regime catalog: Point-in-Time definitions using only contemporaneous inputs.

No predictive edge claims — catalog is descriptive regime measurement only.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_regime_lab.constants import (
    CATALOG_VERSION,
    DEFAULT_BAR_MS,
    DEFAULT_LEAD_LAG_MAX_LAG_BARS,
    DEFAULT_LOOKBACK_BARS,
    DEFAULT_STALE_AFTER_MS,
    NON_CLAIMS,
    REGIME_IDS,
    REGIME_SCHEMA_VERSION,
)

COMMON_SEMANTICS: dict[str, Any] = {
    "timestamp_semantics": {
        "event_time_field": "exchange_timestamp",
        "event_time_unit": "ms_epoch_utc",
        "receive_time_field": "receive_timestamp",
        "receive_time_unit": "ms_epoch_utc",
        "bar_alignment": "floor(exchange_timestamp / bar_ms) * bar_ms",
        "available_at_ms": (
            "max(receive_timestamp) among included bars; regime is not available "
            "before all included bars have been received"
        ),
        "as_of_ms": (
            "Point-in-Time cutoff: only bars with exchange_timestamp <= as_of_ms "
            "AND receive_timestamp <= as_of_ms are eligible"
        ),
    },
    "availability_semantics": {
        "AVAILABLE": "lookback has >= min_bars and required fields parseable",
        "PARTIAL": "lookback has bars but below min_bars or degenerate metrics",
        "MISSING": "no eligible bars in lookback at as_of_ms",
        "NOT_YET_AVAILABLE": "bars exist in event-time but receive_timestamp > as_of_ms",
    },
    "missing_data_behavior": {
        "label": None,
        "metrics": None,
        "availability": "MISSING",
        "does_not_impute": True,
        "does_not_forward_fill": True,
        "does_not_use_future_bars": True,
    },
    "staleness_semantics": {
        "stale_after_ms": DEFAULT_STALE_AFTER_MS,
        "staleness_ms": "as_of_ms - available_at_ms when available_at_ms is known",
        "stale_flag": "True when staleness_ms > stale_after_ms",
        "stale_does_not_change_label": True,
    },
    "lead_lag_semantics": {
        "max_lag_bars_default": DEFAULT_LEAD_LAG_MAX_LAG_BARS,
        "rule": (
            "For lag k>=0, correlate leader[t-k] with follower[t] using only bars "
            "eligible at as_of_ms. Negative lag (follower leads) uses follower[t-k] "
            "vs leader[t]. No bar with exchange or receive > as_of_ms is used."
        ),
        "non_claim": "Lead-lag statistics are descriptive research only; not a trading edge.",
    },
    "non_claims": list(NON_CLAIMS),
}


REGIME_CATALOG: dict[str, dict[str, Any]] = {
    "volatility_regime": {
        "regime_id": "volatility_regime",
        "definition": (
            "Classify realized log-return volatility over the PIT lookback into "
            "LOW | MEDIUM | HIGH using tercile thresholds computed only on the "
            "eligible contemporaneous sample (no future bars)."
        ),
        "units": "categorical_label",
        "inputs": ["close", "exchange_timestamp", "receive_timestamp"],
        "min_bars": 5,
        "value_type": "string",
        "bar_ms_default": DEFAULT_BAR_MS,
        "lookback_bars_default": DEFAULT_LOOKBACK_BARS,
        "labels": ["LOW", "MEDIUM", "HIGH"],
    },
    "liquidity_regime": {
        "regime_id": "liquidity_regime",
        "definition": (
            "Classify average quote notional volume over the PIT lookback into "
            "THIN | NORMAL | DEEP using sample terciles of contemporaneous volume."
        ),
        "units": "categorical_label",
        "inputs": ["volume_notional", "exchange_timestamp", "receive_timestamp"],
        "min_bars": 5,
        "value_type": "string",
        "bar_ms_default": DEFAULT_BAR_MS,
        "lookback_bars_default": DEFAULT_LOOKBACK_BARS,
        "labels": ["THIN", "NORMAL", "DEEP"],
    },
    "trend_regime": {
        "regime_id": "trend_regime",
        "definition": (
            "Signed drift of close over lookback: "
            "(last_close - first_close) / first_close. Labels UP | FLAT | DOWN "
            "using fixed contemporaneous thresholds (±0.001), never future prices."
        ),
        "units": "categorical_label",
        "inputs": ["close", "exchange_timestamp", "receive_timestamp"],
        "min_bars": 3,
        "value_type": "string",
        "bar_ms_default": DEFAULT_BAR_MS,
        "lookback_bars_default": DEFAULT_LOOKBACK_BARS,
        "labels": ["UP", "FLAT", "DOWN"],
    },
    "funding_regime": {
        "regime_id": "funding_regime",
        "definition": (
            "Mean funding rate over PIT-eligible bars: NEGATIVE | NEUTRAL | POSITIVE "
            "using fixed thresholds (±1e-5). Funding observed only when received."
        ),
        "units": "categorical_label",
        "inputs": ["funding_rate", "exchange_timestamp", "receive_timestamp"],
        "min_bars": 3,
        "value_type": "string",
        "bar_ms_default": DEFAULT_BAR_MS,
        "lookback_bars_default": DEFAULT_LOOKBACK_BARS,
        "labels": ["NEGATIVE", "NEUTRAL", "POSITIVE"],
    },
    "open_interest_regime": {
        "regime_id": "open_interest_regime",
        "definition": (
            "Fractional change in open interest over lookback: "
            "(last_oi - first_oi) / first_oi → CONTRACTING | STABLE | EXPANDING "
            "at ±0.01 thresholds. Uses only PIT-eligible OI bars."
        ),
        "units": "categorical_label",
        "inputs": ["open_interest", "exchange_timestamp", "receive_timestamp"],
        "min_bars": 3,
        "value_type": "string",
        "bar_ms_default": DEFAULT_BAR_MS,
        "lookback_bars_default": DEFAULT_LOOKBACK_BARS,
        "labels": ["CONTRACTING", "STABLE", "EXPANDING"],
    },
    "liquidation_regime": {
        "regime_id": "liquidation_regime",
        "definition": (
            "Mean liquidation notional intensity over lookback: QUIET | ELEVATED | "
            "STRESSED using sample terciles of contemporaneous liquidation_notional."
        ),
        "units": "categorical_label",
        "inputs": ["liquidation_notional", "exchange_timestamp", "receive_timestamp"],
        "min_bars": 5,
        "value_type": "string",
        "bar_ms_default": DEFAULT_BAR_MS,
        "lookback_bars_default": DEFAULT_LOOKBACK_BARS,
        "labels": ["QUIET", "ELEVATED", "STRESSED"],
    },
    "correlation_regime": {
        "regime_id": "correlation_regime",
        "definition": (
            "Mean pairwise Pearson correlation of PIT-aligned close returns across "
            "the universe in the lookback: DECOUPLED | MIXED | COUPLED using "
            "fixed thresholds (0.2 / 0.6). Peers missing at as_of are excluded."
        ),
        "units": "categorical_label",
        "inputs": ["close", "symbol", "exchange_timestamp", "receive_timestamp"],
        "min_bars": 5,
        "value_type": "string",
        "bar_ms_default": DEFAULT_BAR_MS,
        "lookback_bars_default": DEFAULT_LOOKBACK_BARS,
        "labels": ["DECOUPLED", "MIXED", "COUPLED"],
    },
    "market_stress_regime": {
        "regime_id": "market_stress_regime",
        "definition": (
            "Composite stress score from contemporaneous volatility z, liquidation "
            "intensity z, and abs(funding) z (equal weight). Labels CALM | WATCH | "
            "STRESS using score terciles on the eligible sample only."
        ),
        "units": "categorical_label",
        "inputs": [
            "close",
            "liquidation_notional",
            "funding_rate",
            "exchange_timestamp",
            "receive_timestamp",
        ],
        "min_bars": 5,
        "value_type": "string",
        "bar_ms_default": DEFAULT_BAR_MS,
        "lookback_bars_default": DEFAULT_LOOKBACK_BARS,
        "labels": ["CALM", "WATCH", "STRESS"],
    },
}


def regime_catalog() -> dict[str, Any]:
    assert set(REGIME_CATALOG) == set(REGIME_IDS)
    return {
        "schema": "v14_f_regime_catalog",
        "catalog_version": CATALOG_VERSION,
        "regime_schema_version": REGIME_SCHEMA_VERSION,
        "common_semantics": COMMON_SEMANTICS,
        "regimes": {
            rid: {**REGIME_CATALOG[rid], "semantics_ref": "common_semantics"}
            for rid in REGIME_IDS
        },
        "regime_count": len(REGIME_IDS),
        "predictive_edge_claimed": False,
        "strategy_signal": False,
        "contemporaneous_only": True,
    }


def require_regime(regime_id: str) -> dict[str, Any]:
    if regime_id not in REGIME_CATALOG:
        raise KeyError(f"unknown_regime:{regime_id}")
    return REGIME_CATALOG[regime_id]
