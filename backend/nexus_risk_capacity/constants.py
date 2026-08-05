"""V15-H Risk and Capacity Review Engine — constants and hard bans."""
from __future__ import annotations

SCHEMA = "FOUNDER_V15_H_RISK_AND_CAPACITY_REVIEW_ENGINE"
CAMPAIGN_ID = "v15_h_risk_capacity_review"
ARTIFACT_DIRNAME = "v15_risk_capacity"
LANE = "V15-H"
LANE_NAME = "RISK_AND_CAPACITY_REVIEW_ENGINE"
BRANCH = "feature/v15-risk-capacity-review"
BASE_COMMIT = "a7c14d9e9004e0e3a6399424fa3375fdea17e367"
RANDOM_SEED = 20260805
DEVELOPMENT_INTERVAL_ID = "DEV_SYNTHETIC_NON_OOS_V15H_2026_08_05"

# Canonical cost authority — consumed, never redefined.
CANONICAL_COST_AUTHORITY = "backend.nexus_execution.cost_model"

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
        "no_strategy_selection",
        "no_ai_override",
        "no_pr27_merge",
        "no_auto_integrate_pr27",
        "no_canonical_cost_formula_mutation",
        "no_fabricated_edge_claims",
        "no_status_json_artifact",
    }
)

OWNED_PATHS = [
    "backend/nexus_risk_capacity",
    "tools/research/risk_capacity",
    "tests/risk_capacity",
    "artifacts/readiness/immutable/v15_risk_capacity",
]

# Founder-required deterministic review dimensions.
REVIEW_DIMENSIONS = (
    "fees",
    "spread",
    "slippage",
    "market_impact",
    "partial_fills",
    "cancel_replace",
    "funding",
    "latency",
    "queue_position",
    "liquidity_collapse",
    "position_concentration",
    "instrument_concentration",
    "regime_concentration",
    "trade_size_capacity",
    "max_drawdown_assumptions",
    "liquidation_distance",
    "missing_data",
    "stale_data",
)

REQUIRED_OUTPUT_KEYS = (
    "gross_expectancy",
    "cost_components",
    "net_expectancy",
    "break_even_cost",
    "maximum_viable_spread",
    "maximum_viable_slippage",
    "capacity_estimate",
    "fragility_score",
    "concentration_review",
    "drawdown_review",
    "liquidation_distance_review",
    "data_quality_review",
    "deterministic_fingerprint",
    "ai_override_attempted",
    "ai_override_applied",
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

# Research-only labels — never qualification / promotion claims.
ALLOWED_LABELS = frozenset(
    {
        "RISK_CAPACITY_OBSERVED",
        "COST_DESTROYED",
        "CAPACITY_LIMITED",
        "CONCENTRATION_BLOCKED",
        "DRAWDOWN_ASSUMPTION_UNSAFE",
        "LIQUIDATION_DISTANCE_UNSAFE",
        "FRAGILE_TO_EXECUTION",
        "DEVELOPMENT_REVIEW_ONLY",
        "INSUFFICIENT_SAMPLE",
        "DATA_QUALITY_BLOCKED",
    }
)

BANNED_CLAIM_FRAGMENTS = frozenset(
    {
        "QUALIFIED",
        "PROFITABLE",
        "OOS_PASS",
        "WALK_FORWARD_PASS",
        "DEMO_READY",
        "PROMOTION_READY",
        "PROMOTED",
        "EDGE_CONFIRMED",
        "ALPHA_PROVEN",
    }
)

FRAGILITY_COST_DESTROY_THRESHOLD = 0.45
CAPACITY_IMPACT_BPS_CAP = 50.0
DEFAULT_BASE_IMPACT_BPS = 2.0

# Hard thresholds for non-execution dimensions (deterministic).
POSITION_CONCENTRATION_LIMIT = 0.35
INSTRUMENT_CONCENTRATION_LIMIT = 0.40
REGIME_CONCENTRATION_LIMIT = 0.55
MAX_DRAWDOWN_ASSUMPTION_LIMIT = 0.20
MIN_LIQUIDATION_DISTANCE_PCT = 5.0
STALE_DATA_MAX_AGE_SEC = 120.0
