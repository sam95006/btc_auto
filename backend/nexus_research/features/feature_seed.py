"""NEXUS Phase 6.5 — Idempotent boot seed for Feature Registry definitions."""
from __future__ import annotations

import logging
from typing import Any

from backend.nexus_research.features.registry import FeatureDefinition, Namespace, get_feature_registry

logger = logging.getLogger(__name__)

FORMULA_VERSION = "1.0.0"
_SEEDED = False

# Phase 6.5 Gate C — initial catalog (stable feature_id = namespace:name)
_PRICE_TECH: list[dict[str, Any]] = [
    ("open", "price", "raw", "1m"),
    ("high", "price", "raw", "1m"),
    ("low", "price", "raw", "1m"),
    ("close", "price", "raw", "1m"),
    ("volume", "price", "raw", "1m"),
    ("turnover", "price", "raw", "1m"),
    ("return_1", "price", "derived", "1m"),
    ("return_5", "price", "derived", "5m"),
    ("sma_20", "technical", "derived", "5m"),
    ("sma_50", "technical", "derived", "5m"),
    ("ema_9", "technical", "derived", "5m"),
    ("ema_21", "technical", "derived", "5m"),
    ("ema_50", "technical", "derived", "5m"),
    ("vwap", "technical", "derived", "5m"),
    ("rsi_14", "technical", "derived", "5m"),
    ("macd", "technical", "derived", "5m"),
    ("macd_signal", "technical", "derived", "5m"),
    ("macd_histogram", "technical", "derived", "5m"),
    ("atr_14", "technical", "derived", "5m"),
    ("adx_14", "technical", "derived", "5m"),
    ("bb_upper", "technical", "derived", "5m"),
    ("bb_middle", "technical", "derived", "5m"),
    ("bb_lower", "technical", "derived", "5m"),
    ("supertrend", "technical", "derived", "5m"),
    ("realized_volatility", "technical", "derived", "5m"),
    ("volume_zscore", "technical", "derived", "5m"),
    ("distance_from_vwap", "technical", "derived", "5m"),
    ("trend_slope", "technical", "derived", "5m"),
]

_ORDER_FLOW: list[tuple[str, str, bool]] = [
    ("best_bid", "order_flow", False),
    ("best_ask", "order_flow", False),
    ("spread", "order_flow", False),
    ("spread_bps", "order_flow", False),
    ("bid_depth", "order_flow", False),
    ("ask_depth", "order_flow", False),
    ("orderbook_imbalance", "order_flow", False),
    ("taker_buy_volume", "order_flow", False),
    ("taker_sell_volume", "order_flow", False),
    ("taker_ratio", "order_flow", False),
    ("cvd", "order_flow", False),
    ("large_buy_count", "order_flow", True),
    ("large_sell_count", "order_flow", True),
    ("buy_liquidity_wall", "order_flow", True),
    ("sell_liquidity_wall", "order_flow", True),
    ("book_update_rate", "order_flow", True),
]

_DERIVATIVES: list[tuple[str, str]] = [
    ("funding_rate", "derivatives"),
    ("funding_change", "derivatives"),
    ("next_funding_time", "derivatives"),
    ("open_interest", "derivatives"),
    ("open_interest_change", "derivatives"),
    ("price_oi_divergence", "derivatives"),
    ("long_short_ratio", "derivatives"),
    ("liquidation_buy_notional", "derivatives"),
    ("liquidation_sell_notional", "derivatives"),
    ("liquidation_imbalance", "derivatives"),
    ("mark_price", "derivatives"),
    ("index_price", "derivatives"),
    ("basis", "derivatives"),
]


def seed_default_feature_definitions(*, force: bool = False) -> dict[str, Any]:
    """Register Phase 6.5 catalog. Idempotent — same IDs on every boot."""
    global _SEEDED
    if _SEEDED and not force:
        reg = get_feature_registry()
        return {"ok": True, "alreadySeeded": True, "count": len(reg.list_definitions())}

    reg = get_feature_registry()
    count_before = len(reg.list_definitions())

    for name, category, raw_or_derived, timeframe in _PRICE_TECH:
        reg.register(
            name,
            Namespace.NATURAL,
            description=f"NEXUS {category} feature {name}",
            version=FORMULA_VERSION,
            tags=[
                category, raw_or_derived, timeframe,
                "used_by_production=false",
                "used_by_shadow=true",
                "phase65_catalog",
            ],
            experimental=False,
        )
        reg.register(
            name,
            Namespace.SHADOW,
            description=f"Shadow mirror of {name}",
            version=FORMULA_VERSION,
            tags=[category, "shadow", "used_by_shadow=true", "used_by_production=false"],
            experimental=False,
        )

    for name, category, experimental in _ORDER_FLOW:
        reg.register(
            name,
            Namespace.NATURAL,
            description=f"Order flow feature {name}",
            version=FORMULA_VERSION,
            tags=[
                category, "order_flow",
                "used_by_production=false",
                "used_by_shadow=true",
                "phase65_catalog",
            ],
            experimental=experimental,
        )

    for name, category in _DERIVATIVES:
        reg.register(
            name,
            Namespace.NATURAL,
            description=f"Derivatives feature {name}",
            version=FORMULA_VERSION,
            tags=[
                category, "derivatives",
                "used_by_production=false",
                "used_by_shadow=true",
                "phase65_catalog",
            ],
            experimental=name.startswith("liquidation"),
        )

    count_after = len(reg.list_definitions())
    _SEEDED = True
    logger.info("[feature_seed] registered %s definitions (+%s)", count_after, count_after - count_before)
    return {
        "ok": True,
        "count": count_after,
        "added": count_after - count_before,
        "formulaVersion": FORMULA_VERSION,
        "researchOnly": True,
    }
