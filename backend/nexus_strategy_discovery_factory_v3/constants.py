"""V13-C Cost-Aware Strategy Discovery Factory V3 — constants & hard bans."""
from __future__ import annotations

PACKAGE = "NEXUS_COST_AWARE_STRATEGY_DISCOVERY_FACTORY_V3"
SCHEMA = "v13_c_strategy_discovery_factory_v3"
CAMPAIGN_ID = "v13_c_strategy_discovery_factory_v3"
ARTIFACT_DIRNAME = "v13_c_strategy_discovery_factory_v3"
RANDOM_SEED = 20260805
DEVELOPMENT_INTERVAL_ID = "DEV_SYNTHETIC_NON_OOS_V13C_2026_08_05"

# Hard bans — development / synthetic / non-OOS only.
HARD_BANS = frozenset(
    {
        "no_oos_consumption",
        "no_formal_walk_forward",
        "no_demo_orders",
        "no_shadow_orders",
        "no_exchange_write",
        "no_mainnet",
        "no_real_money",
        "no_profitability_claims",
        "no_qualified_claims",
        "no_strategy_promotion",
        "no_pr27_merge",
    }
)

ALLOWED_LABELS = frozenset(
    {
        "RESEARCH_SIGNAL_ONLY",
        "RAW_EDGE_PRESENT_BUT_COST_DESTROYED",
        "INSUFFICIENT_SAMPLE",
        "REGIME_FRAGILE",
        "DATA_QUALITY_BLOCKED",
        "DEVELOPMENT_PROMISING_NOT_QUALIFIED",
        "REJECTED",
    }
)

# Explicitly banned vocabulary for this factory.
BANNED_LABEL_FRAGMENTS = frozenset(
    {
        "QUALIFIED",
        "PROFITABLE",
        "OOS_PASS",
        "WALK_FORWARD_PASS",
        "DEMO_READY",
        "PROMOTION_READY",
    }
)

REQUIRED_COST_COMPONENTS = (
    "entry_fee",
    "exit_fee",
    "spread_cost",
    "slippage_cost",
    "funding_cost",
    "partial_fill_cost",
    "cancel_replace_cost",
    "market_impact_approximation",
)

MIN_SAMPLE_TRADES = 12
REGIME_FRAGILITY_SHARE = 0.55
COST_DESTROY_RATIO = 1.0  # gross > 0 and net <= 0 after full costs
STABILITY_FOLD_COUNT = 4

MECHANISM_FAMILIES = (
    "ORDER_FLOW_IMBALANCE",
    "LIQUIDATION_CASCADE",
    "ABSORPTION",
    "AGGRESSION_PERSISTENCE",
    "FUNDING_BASIS_DISLOCATION",
    "VOL_EXPANSION_COMPRESSION",
    "LIQUIDITY_WITHDRAWAL",
    "SPREAD_SHOCK",
    "CROSS_ASSET_LEAD_LAG",
    "REGIME_MEAN_REVERSION",
)
