"""V15-B Mechanism Execution Compiler — constants and hard bans."""
from __future__ import annotations

PACKAGE = "NEXUS_MECHANISM_EXECUTION_COMPILER"
SCHEMA = "v15_b_mechanism_execution_compiler"
LANE = "V15-B"
LANE_NAME = "MECHANISM_EXECUTION_COMPILER"
CAMPAIGN_ID = "v15_b_mechanism_execution_compiler"
ARTIFACT_DIRNAME = "v15_mechanism_execution_compiler"
CATALOG_VERSION = "v15b.1.0"
RANDOM_SEED = 20260805
DEVELOPMENT_INTERVAL_ID = "DEV_SYNTHETIC_NON_OOS_V15B_2026_08_05"
BASE_SHA = "a7c14d9e9004e0e3a6399424fa3375fdea17e367"
BRANCH = "feature/v15-mechanism-execution-compiler"
SOURCE_LANE = "V14-C"
SOURCE_PACKAGE = "NEXUS_STRATEGY_MECHANISM_LAB_V4"
EXPECTED_MECHANISM_COUNT = 42
MIN_EXECUTOR_COUNT = 42

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
        "no_param_only_mechanism_collapse",
    }
)

OWNED_PATHS = (
    "backend/nexus_mechanism_execution_compiler",
    "tools/research/mechanism_execution_compiler",
    "tests/mechanism_execution_compiler",
    "artifacts/readiness/immutable/v15_mechanism_execution_compiler",
)

REQUIRED_EXECUTOR_FIELDS = (
    "executor_id",
    "mechanism_id",
    "family",
    "economic_rationale",
    "input_contract",
    "feature_contract",
    "signal_contract",
    "entry_hypothesis",
    "exit_hypothesis",
    "failure_condition",
    "cost_dependency",
    "risk_compatibility",
    "deterministic_replay",
    "negative_test",
    "economic_rationale_linkage",
)

ALLOWED_LABELS = frozenset(
    {
        "EXECUTOR_COMPILED_DEV_ONLY",
        "CONTROL_OVERLAY_ONLY",
        "COST_GATED",
        "RISK_INCOMPATIBLE_ON_SYNTHETIC",
        "REPLAY_STABLE",
        "NEGATIVE_TEST_COVERED",
        "REJECTED_COMPILE",
    }
)

NON_CLAIMS = (
    "No predictive edge claim",
    "No profitability claim",
    "No qualification claim",
    "Development / synthetic executor surface only",
    "qualification_ready_count must remain 0",
    "Executors are not live trading strategies",
)

# Cost authority consumed, never redefined.
CANONICAL_COST_AUTHORITY = "backend.nexus_execution.cost_model"

# Risk profile vocabulary for compatibility gating (development only).
RISK_PROFILES = (
    "FLOW_MICROSTRUCTURE",
    "LIQUIDATION_STRESS",
    "LIQUIDITY_FRAGILITY",
    "VOLATILITY_REGIME",
    "FUNDING_BASIS",
    "CROSS_ASSET",
    "BREAKOUT_STRUCTURE",
    "VOLUME_OI",
    "IMPACT_PRINT",
    "TIME_OF_DAY",
    "CONTROL_OVERLAY",
)

FAMILY_TO_RISK_PROFILE = {
    "ORDER_FLOW_IMBALANCE": "FLOW_MICROSTRUCTURE",
    "AGGRESSION_PERSISTENCE": "FLOW_MICROSTRUCTURE",
    "FLOW_REVERSAL": "FLOW_MICROSTRUCTURE",
    "LIQUIDATION_CASCADE": "LIQUIDATION_STRESS",
    "POST_LIQUIDATION_EXHAUSTION": "LIQUIDATION_STRESS",
    "ABSORPTION": "FLOW_MICROSTRUCTURE",
    "LIQUIDITY_WITHDRAWAL": "LIQUIDITY_FRAGILITY",
    "SPREAD_SHOCK": "LIQUIDITY_FRAGILITY",
    "VOL_EXPANSION": "VOLATILITY_REGIME",
    "VOL_COMPRESSION": "VOLATILITY_REGIME",
    "FUNDING_DISLOCATION": "FUNDING_BASIS",
    "BASIS_DISLOCATION": "FUNDING_BASIS",
    "CROSS_ASSET_LEAD_LAG": "CROSS_ASSET",
    "REGIME_COND_MEAN_REVERSION": "VOLATILITY_REGIME",
    "BREAKOUT_CONTINUATION": "BREAKOUT_STRUCTURE",
    "FAILED_BREAKOUT": "BREAKOUT_STRUCTURE",
    "VOLUME_PRICE_DIVERGENCE": "VOLUME_OI",
    "OI_DISLOCATION": "VOLUME_OI",
    "MARKET_IMPACT_ASYMMETRY": "IMPACT_PRINT",
    "TIME_OF_DAY": "TIME_OF_DAY",
}

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
