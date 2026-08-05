"""PUB2-I public product analytics — constants, north star, hard bans."""
from __future__ import annotations

LANE = "PUB2-I"
LANE_NAME = "PRODUCT_ANALYTICS_AND_NORTH_STAR_METRICS"
PACKAGE = "NEXUS_PUBLIC_PRODUCT_ANALYTICS_NORTHSTAR_V1"
SCHEMA = "public_product_analytics_metric_schema_v1"
SCHEMA_VERSION = "1.0.0"
BRANCH = "feature/public-v2-product-analytics-northstar"
BASE_COMMIT = "5e93f677ece9f283aeade98657b5e3d5736991b5"

DEPLOYMENT_MODE = "LOCAL_OR_STAGING_ONLY"
PRODUCTION_MODE_FORBIDDEN = True
PRODUCTION_CUSTOMER_DATABASE = False
LIVE_BILLING = False

# Canonical north star (definition only — no fabricated value).
NORTH_STAR_METRIC_ID = "closed_decision_loops_per_active_paid_user"
NORTH_STAR = "CLOSED_DECISION_LOOPS_PER_ACTIVE_PAID_USER"

CLOSED_DECISION_LOOP_REQUIRES: tuple[str, ...] = (
    "decision_created",
    "supporting_evidence",
    "contradicting_evidence",
    "invalidation_conditions",
    "action_or_explicit_no_action",
    "outcome_review",
)

CONSENT_PURPOSE = "product_analytics"

# Event names that feed product metrics (scaffolding catalog).
EVENT_CATALOG: dict[str, dict[str, object]] = {
    "watchlist_activation": {
        "metric_id": "watchlist_activation",
        "description": "Member activated at least one watchlist symbol",
        "allowed_props": ("symbol_count_bucket", "source_surface"),
    },
    "decision_first_opened": {
        "metric_id": "first_decision_opened",
        "description": "First Public Decision Object opened by a consented subject",
        "allowed_props": ("decision_id_hash", "surface"),
    },
    "evidence_engagement": {
        "metric_id": "evidence_engagement",
        "description": "Supporting Evidence panel engagement",
        "allowed_props": ("decision_id_hash", "engagement_kind"),
    },
    "counter_evidence_engagement": {
        "metric_id": "counter_evidence_engagement",
        "description": "Counter-Evidence panel engagement",
        "allowed_props": ("decision_id_hash", "engagement_kind"),
    },
    "task_success": {
        "metric_id": "task_success",
        "description": "Declared product task completed successfully",
        "allowed_props": ("task_id", "success"),
    },
    "session_active": {
        "metric_id": "weekly_active_use",
        "description": "Consented active session heartbeat (WAU input)",
        "allowed_props": ("surface",),
    },
    "decision_review_completed": {
        "metric_id": "decision_review_completion",
        "description": "Outcome / Decision review completed",
        "allowed_props": ("decision_id_hash", "review_kind"),
    },
    "retention_checkpoint": {
        "metric_id": "retention",
        "description": "Retention cohort checkpoint observation",
        "allowed_props": ("cohort_day", "returned"),
    },
    "upgrade_intent": {
        "metric_id": "upgrade_intent",
        "description": "Stated upgrade / paid-intent signal (no live billing)",
        "allowed_props": ("intent_kind", "tier_interest"),
    },
    "validation_conversion": {
        "metric_id": "customer_validation_conversion",
        "description": "Customer validation conversion step (Founder-enrolled only)",
        "allowed_props": ("conversion_step",),
    },
}

METRIC_IDS: tuple[str, ...] = tuple(
    sorted({str(meta["metric_id"]) for meta in EVENT_CATALOG.values()})
)

# Observation status vocabulary — never invent numeric product results.
OBSERVATION_STATUS = (
    "NO_OBSERVATIONS",
    "OBSERVED",
    "CONSENT_DENIED",
    "UNAVAILABLE",
)

HARD_BANS: tuple[str, ...] = (
    "no_merge_pr_26",
    "no_merge_pr_27",
    "no_live_public_deployment",
    "no_app_store_submission",
    "no_google_play_submission",
    "no_live_billing",
    "no_real_iap_products",
    "no_production_customer_database",
    "no_custodial_wallet",
    "no_copy_trading",
    "no_automated_customer_trading",
    "no_fabricated_metrics",
    "no_fabricated_participants",
    "no_fabricated_wau",
    "no_fabricated_conversion_rates",
    "no_pii_in_analytics_props",
    "no_tracking_without_consent",
    "no_exchange_write",
    "no_mainnet",
    "no_real_money",
    "no_demo_order",
    "no_shadow_order",
    "no_status_json_emission",
    "no_private_core_exposure",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_public_product_analytics/",
    "docs/product_analytics/",
    "tests/public_product_analytics/",
)

PRIVATE_CORE_IMPORT_PREFIXES: tuple[str, ...] = (
    "backend.autonomy",
    "backend.execution",
    "backend.decision.private",
    "backend.founder",
    "backend.private",
)

FORBIDDEN_PROP_KEYS: frozenset[str] = frozenset(
    {
        "email",
        "e_mail",
        "phone",
        "phone_number",
        "full_name",
        "name",
        "address",
        "ip",
        "ip_address",
        "ssn",
        "password",
        "api_key",
        "api_secret",
        "private_key",
        "access_token",
        "refresh_token",
        "jwt",
        "wallet_address",
        "exchange_api_key",
        "raw_decision_text",
        "lesson_text",
        "prompt_text",
    }
)

FABRICATED_VALUE_MARKERS: tuple[str, ...] = (
    "fake_",
    "fabricat",
    "synthetic_metric",
    "dummy_wau",
    "placeholder_conversion",
    "invented_",
    "mock_retention",
)
