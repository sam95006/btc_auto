"""V14-E Cost and Execution Sensitivity Lab — constants and hard bans."""
from __future__ import annotations

SCHEMA = "FOUNDER_V14_E_COST_EXECUTION_SENSITIVITY_LAB"
CAMPAIGN_ID = "v14_e_cost_execution_sensitivity"
ARTIFACT_DIRNAME = "v14_cost_sensitivity"
LANE = "V14-E"
LANE_NAME = "COST_AND_EXECUTION_SENSITIVITY_LAB"
BRANCH = "feature/v14-cost-execution-sensitivity"
BASE_COMMIT = "15ecb7b9524d253ec4f2fb04dc73aa1673ec906a"
RANDOM_SEED = 20260805
DEVELOPMENT_INTERVAL_ID = "DEV_SYNTHETIC_NON_OOS_V14E_2026_08_05"

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
        "no_pr27_merge",
        "no_auto_integrate_pr27",
        "no_canonical_cost_formula_mutation",
        "no_fabricated_edge_claims",
        "no_g_source_deletion",
    }
)

OWNED_PATHS = [
    "backend/nexus_cost_sensitivity",
    "tools/research/cost_sensitivity",
    "tests/cost_sensitivity",
    "artifacts/readiness/immutable/v14_cost_sensitivity",
]

# Sensitivity dimensions required by Founder directive.
SENSITIVITY_DIMENSIONS = (
    "maker_taker_mix",
    "spread",
    "slippage",
    "market_impact",
    "partial_fills",
    "cancel_replace",
    "funding",
    "latency",
    "queue_position",
    "liquidity_collapse",
    "trade_size_scaling",
)

# Required per-candidate outputs.
REQUIRED_OUTPUT_KEYS = (
    "gross_expectancy",
    "cost_components",
    "net_expectancy",
    "break_even_cost",
    "maximum_viable_spread",
    "maximum_viable_slippage",
    "capacity_estimate",
    "fragility_score",
)

# CostBridge + explicit research impact approximation (outside CostBridge).
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

# Labels are research-only; never qualification / profitability claims.
ALLOWED_LABELS = frozenset(
    {
        "COST_SENSITIVITY_OBSERVED",
        "COST_DESTROYED",
        "CAPACITY_LIMITED",
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
        "EDGE_CONFIRMED",
        "ALPHA_PROVEN",
    }
)

# Fragility: share of adverse scenarios where net expectancy <= 0.
FRAGILITY_COST_DESTROY_THRESHOLD = 0.45
CAPACITY_IMPACT_BPS_CAP = 50.0
DEFAULT_BASE_IMPACT_BPS = 2.0
