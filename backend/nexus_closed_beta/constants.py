"""Closed-beta invite constants — no fake paid subscriptions, Billing OFF."""
from __future__ import annotations

PACKAGE = "NEXUS_CLOSED_BETA_READINESS_V18_2_22"
SCHEMA = "closed_beta_readiness_v18_2_22"
MARKER = "PUBLIC_V18_2_22_CLOSED_BETA_READINESS_HEAD"

# Member beta access bound to authenticated account (server-authoritative).
BETA_ACCESS_STATUSES = frozenset({"INVITED", "ACTIVE", "REVOKED", "EXPIRED"})

# Invite entity lifecycle (single-use code/token).
INVITE_STATUSES = frozenset({"PENDING", "REDEEMED", "REVOKED", "EXPIRED"})

DEFAULT_INVITE_TTL_SECONDS = 7 * 24 * 3600  # 7 days
CLOSED_BETA_ENFORCED = True
PRODUCTION_BILLING = False
MEMBER_EXECUTION = 0

# Staging-only admin key env for invite mint/revoke (never a partner production token).
ADMIN_INVITE_KEY_ENV = "NEXUS_CLOSED_BETA_ADMIN_KEY"
DEFAULT_STAGING_ADMIN_KEY = "staging-closed-beta-admin"

HARD_BANS = frozenset(
    {
        "no_fake_paid_subscriptions",
        "no_production_billing_activation",
        "no_frontend_plan_authority",
        "no_partner_agent_api_exposure",
        "no_claude_credential_exposure",
        "member_execution_0",
        "mainnet_off",
    }
)

READY_FOR_FOUNDER_VISUAL_REVIEW = "READY_FOR_FOUNDER_VISUAL_REVIEW"
