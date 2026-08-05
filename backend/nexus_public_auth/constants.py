"""PUB2-F public auth entitlement & organization security — constants and hard bans."""
from __future__ import annotations

LANE = "PUB2-F"
LANE_NAME = "AUTH_ENTITLEMENT_AND_ORGANIZATION_SECURITY"
PACKAGE = "NEXUS_PUBLIC_AUTH_ENTITLEMENT_ORG_SECURITY_V2"
SCHEMA = "public_auth_entitlement_org_security_v2"
BRANCH = "feature/public-v2-auth-entitlement-org-security"
BASE_COMMIT = "5e93f677ece9f283aeade98657b5e3d5736991b5"
PRIOR_FOUNDATION = "NEXUS_PUBLIC_AUTH_MEMBERSHIP_FOUNDATION_V1"

# Separate public identity realm — must never equal private issuer realm.
PUBLIC_IDENTITY_REALM = "nexus.public.identity.v1"
PUBLIC_JWT_ISSUER = "nexus-public-auth-v1"
PUBLIC_JWT_AUDIENCE = "nexus-public-member-platform"

# Explicit denylist of private-core issuer / realm identifiers.
PRIVATE_ISSUER_DENYLIST = frozenset(
    {
        "nexus-private",
        "nexus-private-auth",
        "nexus-founder",
        "nexus-operator",
        "nexus.private.identity",
        "nexus.private.identity.v1",
        "private-admin",
        "founder-admin",
        "operator-session",
    }
)

PRIVATE_REALM_DENYLIST = frozenset(
    {
        "nexus.private.identity",
        "nexus.private.identity.v1",
        "nexus.founder.operator",
        "private-operator",
        "founder-private",
    }
)

# Env vars that must never be reused as the public JWT signing material.
PRIVATE_SECRET_ENV_DENYLIST = frozenset(
    {
        "NEXUS_PRIVATE_JWT_SECRET",
        "NEXUS_FOUNDER_JWT_SECRET",
        "NEXUS_OPERATOR_SESSION_SECRET",
        "NEXUS_AUTONOMOUS_DEMO_SESSION_TOKEN",
        "PRIVATE_JWT_SECRET",
        "FOUNDER_JWT_SECRET",
        "OPERATOR_JWT_SECRET",
    }
)

DEPLOYMENT_MODE = "LOCAL_OR_STAGING_ONLY"
PRODUCTION_MODE_FORBIDDEN = True

MEMBERSHIP_TIERS = ("Free", "Pro", "Elite", "Enterprise")

MEMBER_ROLES = frozenset({"member", "member_admin", "support_readonly"})
ORG_ROLES = frozenset({"org_owner", "org_admin", "org_billing_viewer", "org_member"})
TEAM_ROLES = frozenset({"team_lead", "team_reviewer", "team_member"})

CONSENT_PURPOSES = frozenset(
    {
        "terms_of_service",
        "privacy_policy",
        "product_analytics",
        "marketing_email",
        "research_participation",
    }
)

# MFA-ready factor types (abstraction only — no live SMS/TOTP provider required).
MFA_FACTOR_TYPES = frozenset({"totp", "webauthn", "recovery_codes", "email_otp"})
MFA_STATUS_VALUES = frozenset({"disabled", "pending_enrollment", "enabled"})

# Auth API rate-limit defaults (in-memory, non-production).
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_DEFAULTS: dict[str, int] = {
    "register": 10,
    "session_create": 30,
    "session_authenticate": 60,
    "mfa_challenge": 20,
    "export": 5,
    "delete": 5,
    "consent": 30,
    "tier_assign": 10,
}

# Features that must NEVER appear on any public entitlement tier.
# Entitlements gate decision-product reads only — never private execution.
PRIVATE_EXECUTION_FEATURE_DENYLIST = frozenset(
    {
        "private_execution",
        "private_execution_access",
        "execution_write",
        "exchange_write",
        "order_placement",
        "live_trading",
        "mainnet_trading",
        "autonomy_control",
        "founder_operator",
        "checkpoint_mutate",
        "lesson_memory_write",
        "wallet_custody",
        "copy_trading",
        "strategy_promotion",
        "demo_autonomous_control",
        "shadow_control",
    }
)

HARD_BANS = frozenset(
    {
        "no_live_billing",
        "no_real_iap",
        "no_production_customer_database",
        "no_live_public_deployment",
        "no_shared_private_jwt_issuer",
        "no_private_admin_session_reuse",
        "no_private_execution_via_entitlement",
        "no_custodial_wallet",
        "no_copy_trading",
        "no_automated_customer_trading",
        "no_exchange_write",
        "no_mainnet",
        "no_real_money",
        "no_pr26_merge",
        "no_pr27_merge",
    }
)

# Feature matrix — entitlement gates only; no payment collection;
# never includes PRIVATE_EXECUTION_FEATURE_DENYLIST entries.
TIER_FEATURES: dict[str, frozenset[str]] = {
    "Free": frozenset(
        {
            "decision_feed_read",
            "market_overview_read",
            "account_self_service",
            "data_export_self",
            "account_deletion_self",
        }
    ),
    "Pro": frozenset(
        {
            "decision_feed_read",
            "market_overview_read",
            "account_self_service",
            "data_export_self",
            "account_deletion_self",
            "decision_detail_full",
            "evidence_panel",
            "alerts_basic",
            "thesis_monitor",
        }
    ),
    "Elite": frozenset(
        {
            "decision_feed_read",
            "market_overview_read",
            "account_self_service",
            "data_export_self",
            "account_deletion_self",
            "decision_detail_full",
            "evidence_panel",
            "alerts_basic",
            "thesis_monitor",
            "counter_evidence",
            "outcome_review",
            "nex_ai_conversation",
            "alerts_advanced",
            "team_roles",
        }
    ),
    "Enterprise": frozenset(
        {
            "decision_feed_read",
            "market_overview_read",
            "account_self_service",
            "data_export_self",
            "account_deletion_self",
            "decision_detail_full",
            "evidence_panel",
            "alerts_basic",
            "thesis_monitor",
            "counter_evidence",
            "outcome_review",
            "nex_ai_conversation",
            "alerts_advanced",
            "team_roles",
            "org_roles",
            "org_audit_export",
            "sso_placeholder",
            "priority_support_placeholder",
            "mfa_required_org_policy",
        }
    ),
}

BILLING_PROVIDER = "NONE_NON_PRODUCTION"
LIVE_BILLING_ENABLED = False
