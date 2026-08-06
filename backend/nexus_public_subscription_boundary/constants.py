"""PUB17-D Subscription Product Boundary — catalogs and hard bans.

Members may buy intelligence / context products only.
Members must NEVER buy execution or private Founder control products.
"""
from __future__ import annotations

LANE = "PUB17-D"
LANE_NAME = "SUBSCRIPTION_PRODUCT_BOUNDARY"
PACKAGE = "backend.nexus_public_subscription_boundary"
SCHEMA_VERSION = "public_subscription_product_boundary_v1"
BRANCH = "feature/pub17-subscription-product-boundary"
BASE_COMMIT = "8391c17e2d0d0ea9ee69c8e253cc5d71f1456da3"

# Members BUY these (intelligence / context — never execution).
MEMBER_BUYABLE_PRODUCTS: tuple[tuple[str, str], ...] = (
    ("market_data", "Market Data"),
    ("ai_intelligence", "AI Intelligence"),
    ("decision_context", "Decision Context"),
    ("risk_explanation", "Risk Explanation"),
    ("alerts", "Alerts"),
    ("historical_comparisons", "Historical Comparisons"),
    ("global_market_briefs", "Global Market Briefs"),
)

MEMBER_BUYABLE_PRODUCT_IDS: frozenset[str] = frozenset(p[0] for p in MEMBER_BUYABLE_PRODUCTS)
MEMBER_BUYABLE_PRODUCT_LABELS: frozenset[str] = frozenset(p[1] for p in MEMBER_BUYABLE_PRODUCTS)

# Members do NOT buy these (execution / private Founder surfaces).
MEMBER_FORBIDDEN_PRODUCTS: tuple[tuple[str, str], ...] = (
    ("auto_trading", "Auto Trading"),
    ("copy_trading", "Copy Trading"),
    ("exchange_execution", "Exchange Execution"),
    ("private_strategy", "Private Strategy"),
    ("founder_portfolio_access", "Founder Portfolio Access"),
)

MEMBER_FORBIDDEN_PRODUCT_IDS: frozenset[str] = frozenset(
    p[0] for p in MEMBER_FORBIDDEN_PRODUCTS
)
MEMBER_FORBIDDEN_PRODUCT_LABELS: frozenset[str] = frozenset(
    p[1] for p in MEMBER_FORBIDDEN_PRODUCTS
)

# Aliases / smuggling markers that must also be refused as member-buyable.
FORBIDDEN_PRODUCT_ALIASES: frozenset[str] = frozenset(
    {
        "auto_trade",
        "auto-trading",
        "copy_trade",
        "copy-trading",
        "exchange_write",
        "order_placement",
        "live_trading",
        "mainnet_trading",
        "private_execution",
        "execution_controls",
        "execution_control",
        "founder_portfolio",
        "founder_positions",
        "private_strategy_params",
        "strategy_promotion",
        "autonomy_control",
    }
)

# Keys that count toward member_execution_control_count when exposed as
# member-buyable / member-granted / member-nav destinations.
EXECUTION_CONTROL_MARKERS: frozenset[str] = frozenset(
    {
        *MEMBER_FORBIDDEN_PRODUCT_IDS,
        *FORBIDDEN_PRODUCT_ALIASES,
        "place_order",
        "submit_order",
        "create_order",
        "leverage_control",
        "position_control",
        "trade_button",
        "api_key_entry",
    }
)

HARD_BANS: tuple[str, ...] = (
    "no_member_auto_trading",
    "no_member_copy_trading",
    "no_member_exchange_execution",
    "no_member_private_strategy",
    "no_member_founder_portfolio_access",
    "no_member_execution_controls",
    "no_live_billing",
    "no_production_billing_claims",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_exchange_write",
    "no_mainnet",
    "no_real_money",
    "no_acceleration_report_edit",
    "no_consolidated_report_edit",
)

# Web / mobile nav destinations allowed for members (product-linked).
MEMBER_ALLOWED_NAV_PRODUCTS: frozenset[str] = MEMBER_BUYABLE_PRODUCT_IDS | frozenset(
    {
        "home",
        "membership",
        "account",
        "privacy",
        "account_deletion",
        "notification_settings",
        "decision_memory",
        "outcome_review",
        "thesis_monitor",
        "counter_evidence",
        "evidence",
        "nex_ai",
    }
)

LIVE_BILLING_ENABLED = False
BILLING_PROVIDER = "NONE_NON_PRODUCTION"
DEPLOYMENT_MODE = "LOCAL_OR_STAGING_ONLY"
