"""V17-G Gold Feature Factory — single-authority catalog.

One authoritative formula per feature_id. Duplicate registrations of the same
name as a second authority are rejected by the registry guard.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_gold_feature_factory.constants import (
    CATALOG_VERSION,
    FEATURE_IDS,
    FEATURE_SCHEMA_VERSION,
    FEATURE_VERSION,
    MISSING_POLICIES,
)

# Shared semantics for every gold feature.
COMMON_SEMANTICS: dict[str, Any] = {
    "timestamp_semantics": {
        "as_of": "PIT cutoff ms; only bars/events with exchange_ts <= as_of AND receive_ts <= as_of",
        "available_at": "max(receive_ts) among inputs included in the calculation",
        "no_future_price_labels": True,
    },
    "missing_data_behavior": {
        "does_not_silent_forward_fill": True,
        "does_not_impute_zeros": True,
        "unmarked_missing_forbidden": True,
        "allowed_policies": list(MISSING_POLICIES),
        "quality_when_missing": ["UNAVAILABLE", "MISSING", "PARTIAL"],
    },
    "authority": {
        "one_formula_per_feature_id": True,
        "duplicate_authority_rejected": True,
    },
    "non_claims": [
        "No predictive edge",
        "No profitability",
        "No strategy signal",
        "Descriptive gold feature measurement only",
    ],
}


FEATURE_CATALOG: dict[str, dict[str, Any]] = {
    "trend": {
        "feature_id": "trend",
        "definition": (
            "Linear slope of close over lookback bars divided by mean close "
            "(fractional slope). PIT: uses only bars with exchange_ts<=as_of."
        ),
        "units": "fractional_slope",
        "normalization": "mean_scaled_slope",
        "missing_policy": "MARK_UNAVAILABLE",
        "license_scope": "internal_research_fixture",
        "source_lineage": ("fixture.ohlcv.close",),
        "lookback_default": 20,
        "formula_id": "trend.mean_scaled_ols_slope.v1",
    },
    "volatility": {
        "feature_id": "volatility",
        "definition": (
            "Sample std of log returns of close over lookback bars. "
            "Annualization NOT applied; raw window std only."
        ),
        "units": "log_return_std",
        "normalization": "raw_window_std",
        "missing_policy": "MARK_UNAVAILABLE",
        "license_scope": "internal_research_fixture",
        "source_lineage": ("fixture.ohlcv.close",),
        "lookback_default": 20,
        "formula_id": "volatility.log_return_std.v1",
    },
    "liquidity": {
        "feature_id": "liquidity",
        "definition": (
            "Amihud-style illiquidity inverse proxy: mean(volume) / "
            "(1e-12 + mean(abs(log_return))). Higher = more liquid descriptive proxy."
        ),
        "units": "volume_per_abs_log_return",
        "normalization": "amihud_inverse_proxy",
        "missing_policy": "MARK_UNAVAILABLE",
        "license_scope": "internal_research_fixture",
        "source_lineage": ("fixture.ohlcv.close", "fixture.ohlcv.volume"),
        "lookback_default": 20,
        "formula_id": "liquidity.amihud_inverse.v1",
    },
    "spread": {
        "feature_id": "spread",
        "definition": (
            "Mean relative bid-ask spread over lookback: "
            "mean((ask-bid)/mid) using quote rows eligible at as_of."
        ),
        "units": "relative_spread",
        "normalization": "mid_relative_mean",
        "missing_policy": "MARK_UNAVAILABLE",
        "license_scope": "internal_research_fixture",
        "source_lineage": ("fixture.quotes.bid", "fixture.quotes.ask"),
        "lookback_default": 20,
        "formula_id": "spread.relative_mid_mean.v1",
    },
    "turnover": {
        "feature_id": "turnover",
        "definition": "Sum of quote-notional turnover (close*volume) over lookback bars.",
        "units": "quote_notional",
        "normalization": "sum_notional",
        "missing_policy": "MARK_UNAVAILABLE",
        "license_scope": "internal_research_fixture",
        "source_lineage": ("fixture.ohlcv.close", "fixture.ohlcv.volume"),
        "lookback_default": 20,
        "formula_id": "turnover.sum_close_x_volume.v1",
    },
    "funding": {
        "feature_id": "funding",
        "definition": "Latest funding rate at or before as_of (no forward fill of gaps).",
        "units": "funding_rate",
        "normalization": "raw_rate",
        "missing_policy": "MARK_UNAVAILABLE",
        "license_scope": "internal_research_fixture",
        "source_lineage": ("fixture.derivatives.funding_rate",),
        "lookback_default": 1,
        "formula_id": "funding.last_eligible_rate.v1",
    },
    "open_interest": {
        "feature_id": "open_interest",
        "definition": "Latest open interest value at or before as_of (no forward fill).",
        "units": "contracts_or_coin",
        "normalization": "raw_oi",
        "missing_policy": "MARK_UNAVAILABLE",
        "license_scope": "internal_research_fixture",
        "source_lineage": ("fixture.derivatives.open_interest",),
        "lookback_default": 1,
        "formula_id": "open_interest.last_eligible.v1",
    },
    "liquidation": {
        "feature_id": "liquidation",
        "definition": (
            "Sum of liquidation notional in lookback window ending at as_of."
        ),
        "units": "quote_notional",
        "normalization": "sum_notional",
        "missing_policy": "EXCLUDE_WITH_REASON",
        "license_scope": "internal_research_fixture",
        "source_lineage": ("fixture.derivatives.liquidations",),
        "lookback_default": 20,
        "formula_id": "liquidation.window_notional_sum.v1",
    },
    "crowding": {
        "feature_id": "crowding",
        "definition": (
            "Crowding proxy: abs(funding_rate) * open_interest / "
            "(1e-12 + mean_turnover). Descriptive only."
        ),
        "units": "dimensionless_crowding_proxy",
        "normalization": "funding_x_oi_over_turnover",
        "missing_policy": "PROPAGATE_QUALITY",
        "license_scope": "internal_research_fixture",
        "source_lineage": (
            "fixture.derivatives.funding_rate",
            "fixture.derivatives.open_interest",
            "fixture.ohlcv.close",
            "fixture.ohlcv.volume",
        ),
        "lookback_default": 20,
        "formula_id": "crowding.funding_oi_turnover.v1",
    },
    "order_flow": {
        "feature_id": "order_flow",
        "definition": (
            "Signed aggressive flow imbalance: "
            "(buy_notional - sell_notional) / (buy_notional + sell_notional). "
            "UNKNOWN side excluded; never imputed."
        ),
        "units": "dimensionless_ratio_in_[-1,1]",
        "normalization": "signed_notional_imbalance",
        "missing_policy": "MARK_UNAVAILABLE",
        "license_scope": "internal_research_fixture",
        "source_lineage": ("fixture.trades.aggressor_side", "fixture.trades.notional"),
        "lookback_default": 20,
        "formula_id": "order_flow.signed_imbalance.v1",
    },
    "cross_asset": {
        "feature_id": "cross_asset",
        "definition": (
            "Pearson correlation of primary close log-returns vs peer series "
            "over lookback. Requires >= 3 overlapping return pairs."
        ),
        "units": "dimensionless_correlation",
        "normalization": "pearson_log_return_corr",
        "missing_policy": "MARK_UNAVAILABLE",
        "license_scope": "internal_research_fixture",
        "source_lineage": ("fixture.ohlcv.close", "fixture.peer.ohlcv.close"),
        "lookback_default": 20,
        "formula_id": "cross_asset.pearson_log_return.v1",
    },
    "session": {
        "feature_id": "session",
        "definition": (
            "UTC session bucket at as_of: ASIA | EUROPE | US | OFF. "
            "Derived from clock only; not a signal."
        ),
        "units": "categorical_session",
        "normalization": "utc_hour_bucket",
        "missing_policy": "MARK_UNAVAILABLE",
        "license_scope": "internal_research_fixture",
        "source_lineage": ("fixture.clock.as_of",),
        "lookback_default": 0,
        "formula_id": "session.utc_hour_bucket.v1",
    },
    "event_risk": {
        "feature_id": "event_risk",
        "definition": (
            "Count of scheduled macro/crypto events whose announce_ts is within "
            "lookback_ms before as_of and available_at <= as_of."
        ),
        "units": "event_count",
        "normalization": "count",
        "missing_policy": "EXCLUDE_WITH_REASON",
        "license_scope": "internal_research_fixture",
        "source_lineage": ("fixture.events.announce_ts",),
        "lookback_default": 20,
        "formula_id": "event_risk.window_count.v1",
    },
    "market_breadth": {
        "feature_id": "market_breadth",
        "definition": (
            "Fraction of universe symbols with positive lookback return at as_of."
        ),
        "units": "fraction_advancing",
        "normalization": "advancers_over_universe",
        "missing_policy": "PROPAGATE_QUALITY",
        "license_scope": "internal_research_fixture",
        "source_lineage": ("fixture.universe.ohlcv.close",),
        "lookback_default": 20,
        "formula_id": "market_breadth.advancers_fraction.v1",
    },
    "stablecoin_stress": {
        "feature_id": "stablecoin_stress",
        "definition": (
            "Mean absolute peg deviation of listed stables from 1.0 over lookback."
        ),
        "units": "abs_peg_deviation",
        "normalization": "mean_abs_deviation_from_one",
        "missing_policy": "MARK_UNAVAILABLE",
        "license_scope": "internal_research_fixture",
        "source_lineage": ("fixture.stablecoin.price",),
        "lookback_default": 20,
        "formula_id": "stablecoin_stress.mean_abs_peg_dev.v1",
    },
    "data_trust": {
        "feature_id": "data_trust",
        "definition": (
            "Trust score in [0,1] from completeness of required source families "
            "and freshness (available_at vs as_of). Never overrides quality flags."
        ),
        "units": "trust_score_0_1",
        "normalization": "completeness_x_freshness",
        "missing_policy": "PROPAGATE_QUALITY",
        "license_scope": "internal_research_fixture",
        "source_lineage": (
            "fixture.ohlcv",
            "fixture.quotes",
            "fixture.derivatives",
            "fixture.trades",
        ),
        "lookback_default": 20,
        "formula_id": "data_trust.completeness_freshness.v1",
    },
}


def feature_catalog() -> dict[str, Any]:
    assert set(FEATURE_CATALOG) == set(FEATURE_IDS)
    # Enforce single authority: formula_id unique per feature_id, and feature_id unique.
    formula_ids = [m["formula_id"] for m in FEATURE_CATALOG.values()]
    assert len(formula_ids) == len(set(formula_ids))
    return {
        "schema": SCHEMA_NAME(),
        "catalog_version": CATALOG_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_version": FEATURE_VERSION,
        "common_semantics": COMMON_SEMANTICS,
        "features": {
            fid: {**FEATURE_CATALOG[fid], "semantics_ref": "common_semantics"}
            for fid in FEATURE_IDS
        },
        "feature_count": len(FEATURE_IDS),
        "predictive_edge_claimed": False,
        "authoritative_formula_count_per_name": 1,
    }


def SCHEMA_NAME() -> str:
    return "v17_g_gold_feature_catalog"


def require_feature(feature_id: str) -> dict[str, Any]:
    if feature_id not in FEATURE_CATALOG:
        raise KeyError(f"unknown_feature:{feature_id}")
    return FEATURE_CATALOG[feature_id]


def formula_authority_map() -> dict[str, str]:
    """feature_id -> single authoritative formula_id."""
    return {fid: FEATURE_CATALOG[fid]["formula_id"] for fid in FEATURE_IDS}
