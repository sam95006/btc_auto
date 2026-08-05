"""V16-G Uncertainty and Abstention Engine — constants and hard bans."""
from __future__ import annotations

SCHEMA = "FOUNDER_V16_G_UNCERTAINTY_AND_ABSTENTION_ENGINE"
LANE = "V16-G"
LANE_NAME = "UNCERTAINTY_AND_ABSTENTION_ENGINE"
BRANCH = "feature/v16-uncertainty-abstention-engine"
BASE_COMMIT = "f01407e5d7c7e4c00e0eb1616dc5ef74d91a58b5"
CAMPAIGN_ID = "v16_g_uncertainty_abstention"
RANDOM_SEED = 20260806
PASS_COUNT = 3

# Verdict ladder — most severe wins.
VERDICTS = (
    "ALLOW",
    "ALLOW_REDUCED",
    "WAIT",
    "ABSTAIN",
    "BLOCK",
)

VERDICT_SEVERITY = {
    "ALLOW": 0,
    "ALLOW_REDUCED": 1,
    "WAIT": 2,
    "ABSTAIN": 3,
    "BLOCK": 4,
}

# Agreement / quality input channels.
AGREEMENT_CHANNELS = (
    "model_agreement",
    "data_agreement",
    "historical_agreement",
    "regime_agreement",
    "execution_agreement",
    "risk_agreement",
)

QUALITY_CHANNELS = (
    "calibration_reliability",
    "similarity_coverage",
    "prediction_interval_width",
    "data_freshness_sec",
)

REQUIRED_INPUT_KEYS = AGREEMENT_CHANNELS + QUALITY_CHANNELS + (
    "stated_confidence",
    "provider_status",
)

PROVIDER_OK = "OK"
PROVIDER_FAILED = "FAILED"
PROVIDER_TIMEOUT = "TIMEOUT"
PROVIDER_INVALID_JSON = "INVALID_JSON"
PROVIDER_STATUSES = frozenset(
    {
        PROVIDER_OK,
        PROVIDER_FAILED,
        PROVIDER_TIMEOUT,
        PROVIDER_INVALID_JSON,
    }
)

# Deterministic thresholds (fail-closed bias).
AGREEMENT_ALLOW_MIN = 0.80
AGREEMENT_REDUCED_MIN = 0.65
AGREEMENT_WAIT_MIN = 0.50
DATA_AGREEMENT_HARD_MIN = 0.70  # consensus cannot override below this
CALIBRATION_ALLOW_MIN = 0.70
CALIBRATION_DEGRADE_MAX_CONF = 0.80  # high conf + low cal → degrade
CALIBRATION_ABSTAIN_MAX = 0.40
COVERAGE_ALLOW_MIN = 0.60
COVERAGE_ABSTAIN_MAX = 0.25
INTERVAL_ALLOW_MAX = 0.35  # normalized width
INTERVAL_ABSTAIN_MIN = 0.70
FRESHNESS_ALLOW_MAX_SEC = 30.0
FRESHNESS_WAIT_MAX_SEC = 90.0
FRESHNESS_STALE_SEC = 120.0
CONTRADICTION_GAP = 0.35  # max-min agreement gap ⇒ contradiction

HARD_BANS = frozenset(
    {
        "no_fail_open_on_missing_inputs",
        "no_fail_open_on_provider_failure",
        "no_fail_open_on_invalid_json",
        "no_fail_open_on_stale_evidence",
        "no_fail_open_on_contradiction",
        "no_consensus_override_of_bad_data",
        "no_high_confidence_low_calibration_allow",
        "no_ai_override_of_verdict",
        "no_exchange_write",
        "no_mainnet",
        "no_real_money",
        "no_demo_orders",
        "no_shadow_orders",
        "no_oos_consumption",
        "no_formal_walk_forward",
        "no_strategy_promotion",
        "no_auto_integrate",
        "no_status_json_artifact",
        "no_lane_status_report",
        "no_profitability_claims",
        "no_qualified_claims",
    }
)

OWNED_PATHS = [
    "backend/nexus_uncertainty_abstention",
    "tools/research/uncertainty_abstention",
    "tests/uncertainty_abstention",
]

FORBIDDEN_ARTIFACT_SUFFIXES = (
    "_status.json",
    "_report.json",
    "_lane_status.json",
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
