"""PUB-H public auth & membership foundation — constants and hard bans."""
from __future__ import annotations

LANE = "PUB-H"
LANE_NAME = "AUTH_AND_MEMBERSHIP_FOUNDATION"
PACKAGE = "NEXUS_PUBLIC_AUTH_MEMBERSHIP_FOUNDATION_V1"
SCHEMA = "public_auth_membership_foundation_v1"
BRANCH = "feature/public-v1-auth-membership-foundation"
BASE_COMMIT = "39e6b1ae1a40698d02c4cb8de4d80fc412309cfc"

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

HARD_BANS = frozenset(
    {
        "no_live_billing",
        "no_real_iap",
        "no_production_customer_database",
        "no_live_public_deployment",
        "no_shared_private_jwt_issuer",
        "no_private_admin_session_reuse",
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

# Feature matrix — entitlement gates only; no payment collection.
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
        }
    ),
}

BILLING_PROVIDER = "NONE_NON_PRODUCTION"
LIVE_BILLING_ENABLED = False
