"""V18.2 public product surface — plans, data truth, brand/pricing freeze."""
from __future__ import annotations

SCHEMA = "public_entitlements_v18_2_alpha_v1"
POLICY_VERSION = "v18_2_alpha_draft"
PACKAGE = "backend.nexus_public_entitlements_v18_2"
LANE = "V18_2_TRACK_B"
LANE_NAME = "PUBLIC_PRODUCT_SURFACE_MEMBERSHIP"
PUBLIC_BASE_COMMIT = "8f0cfc14dd9b4c6cbf3bf236606d8df7802d8ac7"
BRANCH = "feature/nexus-public-v18-2-product-surface"

MEMBERSHIP_PLANS = ("VISITOR", "FREE", "PRO", "RESEARCH", "ENTERPRISE")

LEGACY_TIER_TO_PLAN = {
    "visitor": "VISITOR",
    "Visitor": "VISITOR",
    "free": "FREE",
    "Free": "FREE",
    "pro": "PRO",
    "Pro": "PRO",
    "elite": "RESEARCH",
    "Elite": "RESEARCH",
    "ELITE_LEGACY": "RESEARCH",
    "research": "RESEARCH",
    "Research": "RESEARCH",
    "enterprise": "ENTERPRISE",
    "Enterprise": "ENTERPRISE",
}

ORG_ROLES = ("ORG_ADMIN", "ANALYST", "VIEWER")

ENTITLEMENT_SOURCES = frozenset(
    {"policy_default", "session", "org_override", "legacy_tier_map", "manual_staging"}
)

# UI / API data-state truth (extends runtime snapshot chrome).
UI_DATA_STATES = frozenset(
    {
        "LIVE",
        "LIVE_PARTIAL_DEGRADED",
        "DELAYED",
        "STALE",
        "STOPPED",
        "UNAVAILABLE",
        "FIXTURE",
        "DEMO_DATA",
    }
)

BRAND_STATUS = "BRAND_TBD"
PRICING_STATUS = "PRICING_TBD"
BILLING_STATUS = "NOT_STARTED"
PRODUCTION_BILLING = False

BRAND_CONFIG = {
    "brand_status": BRAND_STATUS,
    "pricing_status": PRICING_STATUS,
    "billing_status": BILLING_STATUS,
    "brand_display_name": "NEXUS Market Intelligence",
    "brand_short_name": "NEXUS",
    "brand_tagline": None,
    "plan_display_name": "PRICE_TBD",
    "price_display": "PRICE_TBD",
    "currency_display": None,
}

FORBIDDEN_CAPABILITY_IDS = frozenset(
    {
        "TRADE",
        "ORDER",
        "COPY_TRADE",
        "EXCHANGE_CONNECT",
        "WALLET_CONNECT",
        "POSITION_CONTROL",
        "LEVERAGE_CONTROL",
        "RISK_OVERRIDE",
        "STRATEGY_DEPLOY",
        "LESSON_ACTIVATE",
        "FOUNDER_LEDGER_READ",
    }
)

DENIAL_CODES = frozenset({"ENTITLEMENT_REQUIRED", "POLICY_DENIED"})

HARD_BANS = frozenset(
    {
        "no_trade_capabilities",
        "no_production_billing",
        "no_scattered_tier_checks_in_ui",
        "no_fake_analytics_observations",
        "no_founder_secrets_in_enterprise",
        "single_capability_registry",
        "single_entitlement_authority",
    }
)

OWNED_PATHS = (
    "backend/nexus_public_entitlements_v18_2",
    "frontend/src/member/public_entitlements_v18_2",
    "frontend/src/member/navigationContractV18_2.ts",
    "frontend/src/member/UpgradeGate.tsx",
    "apps/nexus_public_mobile/lib/data/dto/public_entitlement_dto.dart",
)
