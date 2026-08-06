"""V17-F Data Quality and Trust Engine V2 — constants and hard bans."""
from __future__ import annotations

SCHEMA = "FOUNDER_V17_F_DATA_QUALITY_AND_TRUST_ENGINE_V2"
LANE = "V17-F"
LANE_NAME = "DATA_QUALITY_AND_TRUST_ENGINE_V2"
BRANCH = "feature/v17-data-trust-engine-v2"
BASE_COMMIT = "66a0f7827d5709fc09bc8c7495e93a4089eb28de"
CAMPAIGN_ID = "v17_f_data_trust"
RANDOM_SEED = 20260806

# Trust ladder (output statuses). Ordering is descriptive, not severity.
TRUST_STATUSES: tuple[str, ...] = (
    "TRUSTED",
    "USABLE_WITH_LIMITS",
    "DEGRADED",
    "STALE",
    "CONFLICTED",
    "LICENSE_BLOCKED",
    "UNAVAILABLE",
)

# Severity: higher = worse. Used when merging channel outcomes.
TRUST_SEVERITY: dict[str, int] = {
    "TRUSTED": 0,
    "USABLE_WITH_LIMITS": 1,
    "DEGRADED": 2,
    "STALE": 3,
    "CONFLICTED": 4,
    "LICENSE_BLOCKED": 5,
    "UNAVAILABLE": 6,
}

# Gated posture when trust dominates AI confidence.
GATE_ACTIONS: tuple[str, ...] = (
    "ALLOW",
    "ALLOW_REDUCED",
    "WAIT",
    "ABSTAIN",
    "BLOCK",
)

GATE_SEVERITY: dict[str, int] = {
    "ALLOW": 0,
    "ALLOW_REDUCED": 1,
    "WAIT": 2,
    "ABSTAIN": 3,
    "BLOCK": 4,
}

# Statuses that force WAIT/ABSTAIN/BLOCK regardless of AI confidence.
DOMINANCE_TRUST_STATUSES: frozenset[str] = frozenset(
    {
        "DEGRADED",
        "STALE",
        "CONFLICTED",
        "LICENSE_BLOCKED",
        "UNAVAILABLE",
    }
)

# Input quality channels (normalized 0..1 unless noted).
QUALITY_SCORE_CHANNELS: tuple[str, ...] = (
    "freshness",
    "completeness",
    "cross_source_agreement",
    "schema_validity",
    "timestamp_integrity",
    "market_coverage",
    "microstructure_availability",
)

# Higher = worse.
INVERSE_SCORE_CHANNELS: tuple[str, ...] = (
    "revision_uncertainty",
    "anomaly_rate",
)

LICENSE_STATUSES: tuple[str, ...] = (
    "APPROVED_PUBLIC",
    "APPROVED_INTERNAL_ONLY",
    "LICENSE_REVIEW_REQUIRED",
    "REDISTRIBUTION_FORBIDDEN",
    "TRAINING_FORBIDDEN",
    "DEPRECATED",
    "UNAVAILABLE",
    "UNKNOWN",
)

LICENSE_BLOCKING_STATUSES: frozenset[str] = frozenset(
    {
        "LICENSE_REVIEW_REQUIRED",
        "UNAVAILABLE",
        "UNKNOWN",
        "DEPRECATED",
    }
)

LICENSE_OK_STATUSES: frozenset[str] = frozenset(
    {
        "APPROVED_PUBLIC",
        "APPROVED_INTERNAL_ONLY",
        "REDISTRIBUTION_FORBIDDEN",  # usable internally; redistribution separate
        "TRAINING_FORBIDDEN",  # usable for non-training paths
    }
)

REQUIRED_INPUT_KEYS: tuple[str, ...] = QUALITY_SCORE_CHANNELS + INVERSE_SCORE_CHANNELS + (
    "license_status",
)

OPTIONAL_INPUT_KEYS: tuple[str, ...] = (
    "ai_confidence",
    "availability",
    "case_id",
    "symbol",
    "source_id",
)

# Deterministic thresholds (fail-closed bias).
FRESHNESS_TRUSTED_MIN = 0.85
FRESHNESS_LIMITS_MIN = 0.65
FRESHNESS_STALE_MAX = 0.40  # below → STALE

COMPLETENESS_TRUSTED_MIN = 0.90
COMPLETENESS_LIMITS_MIN = 0.70
COMPLETENESS_UNAVAILABLE_MAX = 0.15

AGREEMENT_TRUSTED_MIN = 0.85
AGREEMENT_LIMITS_MIN = 0.65
AGREEMENT_CONFLICT_MAX = 0.45  # below → CONFLICTED

SCHEMA_TRUSTED_MIN = 0.99
SCHEMA_DEGRADED_MAX = 0.80

TIMESTAMP_TRUSTED_MIN = 0.99
TIMESTAMP_DEGRADED_MAX = 0.80

REVISION_UNCERTAINTY_TRUSTED_MAX = 0.20
REVISION_UNCERTAINTY_DEGRADED_MIN = 0.55

COVERAGE_TRUSTED_MIN = 0.80
COVERAGE_LIMITS_MIN = 0.55
COVERAGE_DEGRADED_MAX = 0.35

MICRO_TRUSTED_MIN = 0.75
MICRO_LIMITS_MIN = 0.50
MICRO_DEGRADED_MAX = 0.30

ANOMALY_TRUSTED_MAX = 0.10
ANOMALY_DEGRADED_MIN = 0.35

# Trust score composite weights (sum = 1.0).
CHANNEL_WEIGHTS: dict[str, float] = {
    "freshness": 0.14,
    "completeness": 0.12,
    "cross_source_agreement": 0.14,
    "schema_validity": 0.12,
    "timestamp_integrity": 0.12,
    "revision_uncertainty": 0.08,  # inverted
    "market_coverage": 0.10,
    "microstructure_availability": 0.08,
    "anomaly_rate": 0.10,  # inverted
}

HARD_BANS: frozenset[str] = frozenset(
    {
        "no_ai_confidence_override_of_degraded_trust",
        "no_fail_open_on_missing_inputs",
        "no_license_unknown_as_trusted",
        "no_license_review_as_trusted",
        "no_exchange_write",
        "no_mainnet",
        "no_real_money",
        "no_demo_orders",
        "no_pr26_merge",
        "no_pr27_merge",
        "no_acceleration_report_edit",
        "no_status_json_artifact",
        "no_profitability_claims",
        "no_qualified_claims",
    }
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_data_trust_engine_v2",
    "tools/research/data_trust_engine_v2",
    "tests/data_trust_engine_v2",
)

FORBIDDEN_ARTIFACT_SUFFIXES: tuple[str, ...] = (
    "_status.json",
    "_report.json",
    "_lane_status.json",
)

BANNED_CLAIM_FRAGMENTS: frozenset[str] = frozenset(
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
