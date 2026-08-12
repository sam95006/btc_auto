"""Feature catalog: definitions, units, and timestamp/availability/missing/staleness semantics.

No predictive edge claims — catalog is descriptive measurement only.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_micro_feature_lab.constants import (
    CATALOG_VERSION,
    DEFAULT_STALE_AFTER_MS,
    DEFAULT_WINDOW_MS,
    FEATURE_IDS,
    FEATURE_SCHEMA_VERSION,
)

# Shared semantic contract applied to every feature observation.
COMMON_SEMANTICS: dict[str, Any] = {
    "timestamp_semantics": {
        "event_time_field": "exchange_timestamp",
        "event_time_unit": "ms_epoch_utc",
        "receive_time_field": "receive_timestamp",
        "receive_time_unit": "ms_epoch_utc",
        "window_alignment": "floor(exchange_timestamp / window_ms) * window_ms",
        "feature_event_timestamp": "max(exchange_timestamp) among events included in the window",
        "available_at_ms": (
            "max(receive_timestamp) among included events; feature is not available "
            "before all included events have been received"
        ),
        "as_of_ms": (
            "Point-in-Time cutoff: only events with exchange_timestamp <= as_of_ms "
            "AND receive_timestamp <= as_of_ms are eligible"
        ),
    },
    "availability_semantics": {
        "AVAILABLE": "window has >= min_events and side/price fields parseable where required",
        "PARTIAL": "window has events but below min_events or required fields missing for subset",
        "MISSING": "no eligible events in window at as_of_ms",
        "NOT_YET_AVAILABLE": "eligible events exist in event-time but receive_timestamp > as_of_ms",
    },
    "missing_data_behavior": {
        "value": None,
        "availability": "MISSING",
        "does_not_impute": True,
        "does_not_forward_fill": True,
        "does_not_invent_aggressor_side": True,
    },
    "staleness_semantics": {
        "stale_after_ms": DEFAULT_STALE_AFTER_MS,
        "staleness_ms": "as_of_ms - available_at_ms when available_at_ms is known",
        "stale_flag": "True when staleness_ms > stale_after_ms",
        "stale_does_not_change_value": True,
        "note": "Staleness is a consumption warning, not a rewrite of the measurement",
    },
    "non_claims": [
        "No predictive edge",
        "No profitability",
        "No strategy signal",
        "Descriptive microstructure measurement only",
    ],
}


FEATURE_CATALOG: dict[str, dict[str, Any]] = {
    "aggressive_buy_sell_imbalance": {
        "feature_id": "aggressive_buy_sell_imbalance",
        "definition": (
            "Net aggressive notional imbalance in the window: "
            "(buy_aggressor_notional - sell_aggressor_notional) / "
            "(buy_aggressor_notional + sell_aggressor_notional). "
            "UNKNOWN aggressor sides are excluded from numerator and denominator."
        ),
        "units": "dimensionless_ratio_in_[-1,1]",
        "inputs": ["AGGRESSIVE_TRADE_FLOW"],
        "min_events": 1,
        "value_type": "float",
        "window_ms_default": DEFAULT_WINDOW_MS,
    },
    "trade_intensity": {
        "feature_id": "trade_intensity",
        "definition": (
            "Trade arrival rate: trade_count / (window_ms / 1000). "
            "Counts AGGRESSIVE_TRADE_FLOW events in the window."
        ),
        "units": "trades_per_second",
        "inputs": ["AGGRESSIVE_TRADE_FLOW"],
        "min_events": 0,
        "value_type": "float",
        "window_ms_default": DEFAULT_WINDOW_MS,
    },
    "trade_size_distribution": {
        "feature_id": "trade_size_distribution",
        "definition": (
            "Empirical size distribution of aggressive trades in the window: "
            "count, mean, std, p50, p90, p99 of notional (quote currency)."
        ),
        "units": "quote_notional_statistics",
        "inputs": ["AGGRESSIVE_TRADE_FLOW"],
        "min_events": 1,
        "value_type": "object",
        "window_ms_default": DEFAULT_WINDOW_MS,
    },
    "liquidation_intensity": {
        "feature_id": "liquidation_intensity",
        "definition": (
            "Liquidation arrival rate: liquidation_count / (window_ms / 1000)."
        ),
        "units": "liquidations_per_second",
        "inputs": ["LIQUIDATION_EVENTS"],
        "min_events": 0,
        "value_type": "float",
        "window_ms_default": DEFAULT_WINDOW_MS,
    },
    "liquidation_clustering": {
        "feature_id": "liquidation_clustering",
        "definition": (
            "Clustering proxy: max liquidations in any sub-bucket of length "
            "cluster_bucket_ms, divided by expected uniform count "
            "(liquidation_count * cluster_bucket_ms / window_ms). "
            "Equals 1 under uniform spacing; >1 indicates clustering."
        ),
        "units": "dimensionless_cluster_ratio",
        "inputs": ["LIQUIDATION_EVENTS"],
        "min_events": 2,
        "value_type": "float",
        "window_ms_default": DEFAULT_WINDOW_MS,
        "cluster_bucket_ms_default": 5_000,
    },
    "flow_persistence": {
        "feature_id": "flow_persistence",
        "definition": (
            "Sign persistence of net aggressive notional across consecutive "
            "sub-windows of length sub_window_ms inside the parent window. "
            "fraction of adjacent sub-window pairs whose net-flow signs agree "
            "(zero-net sub-windows excluded from pairs)."
        ),
        "units": "dimensionless_fraction_in_[0,1]",
        "inputs": ["AGGRESSIVE_TRADE_FLOW"],
        "min_events": 2,
        "value_type": "float",
        "window_ms_default": DEFAULT_WINDOW_MS,
        "sub_window_ms_default": 10_000,
    },
    "flow_reversal": {
        "feature_id": "flow_reversal",
        "definition": (
            "Complement of flow_persistence among comparable adjacent pairs: "
            "1 - persistence when comparable pairs exist; MISSING otherwise."
        ),
        "units": "dimensionless_fraction_in_[0,1]",
        "inputs": ["AGGRESSIVE_TRADE_FLOW"],
        "min_events": 2,
        "value_type": "float",
        "window_ms_default": DEFAULT_WINDOW_MS,
        "sub_window_ms_default": 10_000,
    },
    "price_impact": {
        "feature_id": "price_impact",
        "definition": (
            "Signed mid-path impact over the window: "
            "(last_trade_price - first_trade_price) / first_trade_price, "
            "using exchange event order within the window."
        ),
        "units": "fractional_price_change",
        "inputs": ["AGGRESSIVE_TRADE_FLOW"],
        "min_events": 2,
        "value_type": "float",
        "window_ms_default": DEFAULT_WINDOW_MS,
    },
    "absorption_proxy": {
        "feature_id": "absorption_proxy",
        "definition": (
            "Absorption proxy: abs(net_aggressive_notional) / "
            "(1e-12 + abs(price_change_fraction) * mid_price_proxy * total_volume). "
            "High values indicate large aggressive flow with small price move "
            "(descriptive only; not a liquidity claim)."
        ),
        "units": "dimensionless_absorption_ratio",
        "inputs": ["AGGRESSIVE_TRADE_FLOW"],
        "min_events": 2,
        "value_type": "float",
        "window_ms_default": DEFAULT_WINDOW_MS,
    },
    "vol_adjusted_flow": {
        "feature_id": "vol_adjusted_flow",
        "definition": (
            "Net aggressive notional divided by realized volatility proxy "
            "(std of log returns of successive trade prices in the window). "
            "If realized_vol == 0, availability is PARTIAL and value is None."
        ),
        "units": "quote_notional_per_log_return_std",
        "inputs": ["AGGRESSIVE_TRADE_FLOW"],
        "min_events": 3,
        "value_type": "float",
        "window_ms_default": DEFAULT_WINDOW_MS,
    },
    "cross_symbol_flow": {
        "feature_id": "cross_symbol_flow",
        "definition": (
            "For a primary symbol, Pearson correlation of its per-sub-window "
            "net aggressive notional series with each peer symbol over the same "
            "parent window. Returns {peer: corr} for peers with >= 3 overlapping "
            "non-zero-variance sub-windows."
        ),
        "units": "dimensionless_correlation_map",
        "inputs": ["AGGRESSIVE_TRADE_FLOW"],
        "min_events": 3,
        "value_type": "object",
        "window_ms_default": DEFAULT_WINDOW_MS,
        "sub_window_ms_default": 10_000,
    },
    "regime_context": {
        "feature_id": "regime_context",
        "definition": (
            "Descriptive regime label from trade intensity and realized vol terciles "
            "computed on the fixture/sample distribution within the extraction run: "
            "LOW_ACTIVITY | BALANCED | HIGH_ACTIVITY_HIGH_VOL | HIGH_ACTIVITY_LOW_VOL | "
            "SPARSE. Labels are relative to the provided sample, not market truth."
        ),
        "units": "categorical_label",
        "inputs": ["AGGRESSIVE_TRADE_FLOW"],
        "min_events": 0,
        "value_type": "string",
        "window_ms_default": DEFAULT_WINDOW_MS,
    },
}


def feature_catalog() -> dict[str, Any]:
    assert set(FEATURE_CATALOG) == set(FEATURE_IDS)
    return {
        "schema": "v13_e_micro_feature_catalog",
        "catalog_version": CATALOG_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "common_semantics": COMMON_SEMANTICS,
        "features": {fid: {**FEATURE_CATALOG[fid], **{"semantics_ref": "common_semantics"}} for fid in FEATURE_IDS},
        "feature_count": len(FEATURE_IDS),
        "predictive_edge_claimed": False,
        "strategy_signal": False,
    }


def require_feature(feature_id: str) -> dict[str, Any]:
    if feature_id not in FEATURE_CATALOG:
        raise KeyError(f"unknown_feature:{feature_id}")
    return FEATURE_CATALOG[feature_id]
