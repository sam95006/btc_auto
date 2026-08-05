"""V14-D Robustness and Multiple-Testing Lab — constants & hard bans."""
from __future__ import annotations

PACKAGE = "NEXUS_ROBUSTNESS_MULTIPLE_TESTING_LAB_V14_D"
SCHEMA = "v14_d_robustness_multiple_testing_lab"
CAMPAIGN_ID = "v14_d_robustness_multiple_testing"
ARTIFACT_DIRNAME = "v14_robustness"
LANE = "V14-D"
LANE_NAME = "ROBUSTNESS_AND_MULTIPLE_TESTING_LAB"
BRANCH = "feature/v14-robustness-multiple-testing"
BASE_COMMIT = "15ecb7b9524d253ec4f2fb04dc73aa1673ec906a"
RANDOM_SEED = 20260805
DEVELOPMENT_INTERVAL_ID = "DEV_SYNTHETIC_NON_OOS_V14D_2026_08_05"

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
        "no_auto_integrate",
    }
)

ALLOWED_LABELS = frozenset(
    {
        "DEVELOPMENT_ROBUST",
        "DEVELOPMENT_FRAGILE",
        "MULTIPLE_TESTING_REJECTED",
        "INSUFFICIENT_SAMPLE",
        "COST_DESTROYED",
        "DATA_QUALITY_BLOCKED",
    }
)

BANNED_LABEL_FRAGMENTS = frozenset(
    {
        "QUALIFIED",
        "PROFITABLE",
        "OOS_PASS",
        "WALK_FORWARD_PASS",
        "DEMO_READY",
        "PROMOTION_READY",
        "PROMOTED",
    }
)

OWNED_PATHS = [
    "backend/nexus_research_validation/",
    "tools/research/robustness/",
    "tests/research_validation/",
    "artifacts/readiness/immutable/v14_robustness/",
]

# FDR / multiple testing
FDR_Q_LEVEL = 0.10
BONFERRONI_ALPHA = 0.05

# Bootstrap / block-bootstrap
BOOTSTRAP_REPLICATES = 200
BLOCK_BOOTSTRAP_BLOCK_SIZE = 8
BOOTSTRAP_CI_LEVEL = 0.90
BOOTSTRAP_STABILITY_CI_FLOOR = 0.0  # CI lower bound must be > floor for robust

# Time-series dependence
MAX_ACF_LAG = 12
ACF_DEPENDENCE_THRESHOLD = 0.35

# Stability
PARAM_NEIGHBORHOOD_RADIUS = 0.15  # ±15% parameter perturbation
PARAM_NEIGHBORHOOD_MIN_SIGN_AGREE = 0.70
REGIME_STABILITY_MIN_SHARE = 0.40  # max single-regime concentration for robust
SYMBOL_STABILITY_MIN_SHARE = 0.55  # min symbols with positive net for robust

# Sample size
MIN_SAMPLE_OBSERVATIONS = 48
MIN_SAMPLE_TRADES = 16
MIN_EFFECTIVE_SAMPLE_AFTER_DEPENDENCE = 24

# Cost / turnover
COST_DESTROY_GROSS_POSITIVE_NET_NONPOSITIVE = True
TURNOVER_COST_RATIO_DESTROY = 1.0  # turnover_cost / abs(gross) >= 1 destroys

# Clustering
CORRELATION_CLUSTER_THRESHOLD = 0.80

RESEARCH_FAMILIES = (
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

REQUIRED_COST_COMPONENTS = (
    "entry_fee",
    "exit_fee",
    "spread_cost",
    "slippage_cost",
    "funding_cost",
    "partial_fill_cost",
    "cancel_replace_cost",
    "market_impact_approximation",
    "turnover_cost",
)
