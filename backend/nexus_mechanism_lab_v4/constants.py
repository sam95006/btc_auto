"""V14-C Strategy Mechanism Lab V4 — constants and hard bans."""
from __future__ import annotations

PACKAGE = "NEXUS_STRATEGY_MECHANISM_LAB_V4"
SCHEMA = "v14_c_strategy_mechanism_lab_v4"
LANE = "V14-C"
LANE_NAME = "STRATEGY_MECHANISM_LAB_V4"
CAMPAIGN_ID = "v14_c_strategy_mechanism_lab_v4"
ARTIFACT_DIRNAME = "v14_mechanism_lab_v4"
CATALOG_VERSION = "v4.0.0"
RANDOM_SEED = 20260805
DEVELOPMENT_INTERVAL_ID = "DEV_SYNTHETIC_NON_OOS_V14C_2026_08_05"
BASE_SHA = "15ecb7b9524d253ec4f2fb04dc73aa1673ec906a"
BRANCH = "feature/v14-strategy-mechanism-lab-v4"
MIN_MECHANISM_COUNT = 40

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
        "no_edge_claims",
        "no_qualified_claims",
        "no_strategy_promotion",
        "no_pr27_merge",
        "no_auto_integrate",
    }
)

MECHANISM_FAMILIES = (
    "ORDER_FLOW_IMBALANCE",
    "AGGRESSION_PERSISTENCE",
    "FLOW_REVERSAL",
    "LIQUIDATION_CASCADE",
    "POST_LIQUIDATION_EXHAUSTION",
    "ABSORPTION",
    "LIQUIDITY_WITHDRAWAL",
    "SPREAD_SHOCK",
    "VOL_EXPANSION",
    "VOL_COMPRESSION",
    "FUNDING_DISLOCATION",
    "BASIS_DISLOCATION",
    "CROSS_ASSET_LEAD_LAG",
    "REGIME_COND_MEAN_REVERSION",
    "BREAKOUT_CONTINUATION",
    "FAILED_BREAKOUT",
    "VOLUME_PRICE_DIVERGENCE",
    "OI_DISLOCATION",
    "MARKET_IMPACT_ASYMMETRY",
    "TIME_OF_DAY",
)

REQUIRED_MECHANISM_FIELDS = (
    "mechanism_id",
    "family",
    "economic_rationale",
    "required_data",
    "pit_semantics",
    "entry_hypothesis",
    "exit_hypothesis",
    "failure_hypothesis",
    "cost_sensitivity",
    "capacity_assumptions",
    "invalidating_conditions",
)

NON_CLAIMS = (
    "No predictive edge claim",
    "No profitability claim",
    "No qualification claim",
    "Development / synthetic research surface only",
    "qualification_ready_count must remain 0",
)
