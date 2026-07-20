"""NEXUS Phase 6.4 — Feature Foundation Public API.

Exports the public API for the nexus_research.features package.
"""
from __future__ import annotations

from backend.nexus_research.features.indicators import (
    FORMULA_VERSION,
    sma,
    sma_series,
    ema,
    ema_series,
    vwap,
    rsi,
    macd,
    atr,
    adx,
    bollinger,
    supertrend,
    returns,
    realized_vol,
    volume_zscore,
    price_dist_from_vwap,
    trend_slope,
    compute_all,
)
from backend.nexus_research.features.registry import (
    Namespace,
    FeatureDefinition,
    FeatureObservation,
    FeatureSnapshot,
    FeatureRegistry,
    get_feature_registry,
)
from backend.nexus_research.features.order_flow import (
    OrderBookState,
    TradeFlow,
    DEFAULT_MAX_LEVELS,
    DEFAULT_CVD_WINDOW,
    DEFAULT_LARGE_TRADE_MULTIPLIER,
)
from backend.nexus_research.features.derivatives import (
    normalize_funding,
    normalize_open_interest,
    normalize_long_short_ratio,
    normalize_liquidations,
    normalize_mark_index_basis,
    normalize_derivatives_snapshot,
)
from backend.nexus_research.features.market_intelligence import (
    build_market_sentiment_index,
    build_altcoin_breadth_index,
    build_overall_market_direction,
    build_market_intelligence_summary,
)
from backend.nexus_research.features.shadow_evaluation import (
    ShadowFeatureEvaluation,
    ProductionMutationError,
    get_shadow_evaluator,
)

__all__ = [
    # indicators
    "FORMULA_VERSION",
    "sma", "sma_series", "ema", "ema_series", "vwap",
    "rsi", "macd", "atr", "adx", "bollinger", "supertrend",
    "returns", "realized_vol", "volume_zscore",
    "price_dist_from_vwap", "trend_slope", "compute_all",
    # registry
    "Namespace",
    "FeatureDefinition", "FeatureObservation", "FeatureSnapshot",
    "FeatureRegistry", "get_feature_registry",
    # order flow
    "OrderBookState", "TradeFlow",
    "DEFAULT_MAX_LEVELS", "DEFAULT_CVD_WINDOW", "DEFAULT_LARGE_TRADE_MULTIPLIER",
    # derivatives
    "normalize_funding", "normalize_open_interest",
    "normalize_long_short_ratio", "normalize_liquidations",
    "normalize_mark_index_basis", "normalize_derivatives_snapshot",
    # market intelligence
    "build_market_sentiment_index", "build_altcoin_breadth_index",
    "build_overall_market_direction", "build_market_intelligence_summary",
    # shadow evaluation
    "ShadowFeatureEvaluation", "ProductionMutationError", "get_shadow_evaluator",
]

PHASE = "6.4"
FEATURE_FOUNDATION_VERSION = "1.0.0"
RESEARCH_ONLY = True
