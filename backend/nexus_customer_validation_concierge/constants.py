"""PUB2-G Customer Validation Concierge App — constants and hard bans."""
from __future__ import annotations

SCHEMA_VERSION = "public_v2_customer_validation_concierge_v1"
PACKAGE = "backend.nexus_customer_validation_concierge"
LANE = "PUB2-G"
LANE_NAME = "CUSTOMER_VALIDATION_CONCIERGE_APP"
BRANCH = "feature/public-v2-customer-validation-concierge"
BASE_COMMIT = "5e93f677ece9f283aeade98657b5e3d5736991b5"
API_PREFIX = "/api/public/v2/concierge-validation"

WORKFLOW_STEPS: tuple[str, ...] = (
    "consent",
    "interview",
    "problem_ranking",
    "watchlist_onboarding",
    "decision_object_delivery",
    "weekly_review",
    "retention",
    "willingness_to_pay",
    "objections",
    "pilot_conversion",
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
    "no_fabricated_participants",
    "no_fabricated_interviews",
    "no_fabricated_paid_pilots",
    "no_fabricated_metrics",
    "no_exchange_write",
    "no_mainnet",
    "no_real_money",
    "no_demo_order",
    "no_shadow_order",
    "no_private_core_exposure",
    "local_staging_only",
)

PRIVATE_CORE_IMPORT_PREFIXES: tuple[str, ...] = (
    "backend.trading",
    "backend.fleets",
    "backend.wallet",
    "backend.nexus_demo_execution",
    "backend.nexus_autonomy",
    "backend.nexus_execution",
    "backend.nexus_research_validation",
    "backend.governance",
)

FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "password",
        "private_key",
        "authorization",
        "strategy_parameters",
        "strategy_weights",
        "account_balance",
        "wallet_address",
        "lesson_memory_private",
        "order_id",
        "client_order_id",
        "exchange_order_id",
    }
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_customer_validation_concierge",
    "tools/customer_validation",
    "tools/customer_validation_concierge",
    "tests/test_customer_validation_operations.py",
    "tests/test_pub2_g_customer_validation_concierge.py",
)

ALLOWED_ENVIRONMENTS: frozenset[str] = frozenset(
    {
        "local",
        "local_staging",
        "staging",
        "test",
        "dev",
        "development",
    }
)
