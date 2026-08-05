"""V15-D Research Meta-Analysis and False Discovery — constants & hard bans."""
from __future__ import annotations

PACKAGE = "NEXUS_RESEARCH_META_ANALYSIS_FALSE_DISCOVERY_V15_D"
SCHEMA = "v15_d_research_meta_analysis"
CAMPAIGN_ID = "v15_d_research_meta_analysis"
ARTIFACT_DIRNAME = "v15_research_meta_analysis"
LANE = "V15-D"
LANE_NAME = "RESEARCH_META_ANALYSIS_AND_FALSE_DISCOVERY"
BRANCH = "feature/v15-research-meta-analysis"
BASE_COMMIT = "a7c14d9e9004e0e3a6399424fa3375fdea17e367"
RANDOM_SEED = 20260805
DEVELOPMENT_INTERVAL_ID = "DEV_SYNTHETIC_NON_OOS_V15D_2026_08_05"

HARD_BANS = frozenset(
    {
        "no_oos_consumption",
        "no_oos_execution",
        "no_oos_reservation",
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
        "no_silent_favorable_run_selection",
        "no_promising_without_failed_siblings",
        "no_lane_status_json",
    }
)

ALLOWED_LABELS = frozenset(
    {
        "DEVELOPMENT_PROMISING_NOT_QUALIFIED",
        "DEVELOPMENT_REVIEW",
        "MULTIPLE_TESTING_REJECTED",
        "REGIME_FRAGILE",
        "COST_DESTROYED",
        "CAPACITY_FRAGILE",
        "DUPLICATE_EXPERIMENT",
        "FAVORABLE_SELECTION_BLOCKED",
        "SIBLING_RETENTION_FAILED",
        "INSUFFICIENT_STABILITY",
        "REJECTED",
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
    "backend/nexus_research_meta_analysis/",
    "tools/research/meta_analysis/",
    "tests/research_meta_analysis/",
    "artifacts/readiness/immutable/v15_research_meta_analysis/",
]

# FDR / multiple testing
FDR_Q_LEVEL = 0.10
BONFERRONI_ALPHA = 0.05

# Bootstrap / block-bootstrap
BOOTSTRAP_REPLICATES = 200
BLOCK_BOOTSTRAP_BLOCK_SIZE = 8
BOOTSTRAP_CI_LEVEL = 0.90
BOOTSTRAP_STABILITY_CI_FLOOR = 0.0

# Correlation
CANDIDATE_CORR_THRESHOLD = 0.80
FAMILY_CORR_THRESHOLD = 0.70

# Stability axes
PARAM_NEIGHBORHOOD_RADIUS = 0.15
PARAM_NEIGHBORHOOD_MIN_SIGN_AGREE = 0.70
REGIME_STABILITY_MAX_CONCENTRATION = 0.55
SYMBOL_STABILITY_MIN_POSITIVE_SHARE = 0.55
TURNOVER_STABILITY_MAX_RATIO = 0.85
COST_SENSITIVITY_DESTROY_NET_NONPOSITIVE = True
CAPACITY_MAX_NOTIONAL_SHARE = 0.40  # fragility if capacity assumption concentrates

# Duplication
DUPLICATE_IDENTITY_CORR_FLOOR = 0.95
DUPLICATE_PARAM_DISTANCE_MAX = 0.05

PROMISING_LABELS = frozenset(
    {
        "DEVELOPMENT_PROMISING_NOT_QUALIFIED",
        "DEVELOPMENT_REVIEW",
    }
)

REQUIRED_ANALYSIS_AXES = (
    "candidate_correlation",
    "mechanism_family_correlation",
    "parameter_neighborhood_stability",
    "symbol_stability",
    "regime_stability",
    "turnover_stability",
    "cost_sensitivity",
    "capacity_sensitivity",
    "bootstrap_intervals",
    "block_bootstrap_intervals",
    "false_discovery_adjustment",
    "experiment_duplication",
    "favorable_run_selection_detection",
    "failed_sibling_retention",
)
