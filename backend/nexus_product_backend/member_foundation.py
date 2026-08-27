"""Canonical V1 member identity, role, and entitlement helpers.

This module builds on the existing PostgreSQL-backed product auth foundation.
It contains no billing provider, email provider, trading runtime, or exchange
write authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


CANONICAL_ACCOUNT_STATES = ("ACTIVE", "DISABLED", "PENDING_VERIFICATION")
ACTIVE_ACCOUNT_STATUSES = frozenset({"active", "ACTIVE"})
DISABLED_ACCOUNT_STATUSES = frozenset({"disabled", "DISABLED", "suspended", "SUSPENDED"})
PENDING_ACCOUNT_STATUSES = frozenset(
    {"pending", "PENDING", "pending_verification", "PENDING_VERIFICATION", "unverified", "UNVERIFIED"}
)

CANONICAL_MEMBER_ROLES = ("MEMBER", "FOUNDER_ADMIN")
FOUNDER_ROLE_IDS = frozenset({"role_founder", "FOUNDER_ADMIN", "founder_admin"})
MEMBER_ROLE_IDS = frozenset({"role_member", "role_admin", "MEMBER", "member"})

CANONICAL_PLANS = ("BEGINNER", "INTERMEDIATE", "PRO", "ENTERPRISE")
PLAN_PRIORITY = {plan: idx for idx, plan in enumerate(CANONICAL_PLANS)}
LEGACY_PLAN_ALIASES = {
    "VISITOR": "BEGINNER",
    "FREE": "BEGINNER",
    "STARTER": "BEGINNER",
    "BEGINNER": "BEGINNER",
    "ADVANCED": "INTERMEDIATE",
    "INTERMEDIATE": "INTERMEDIATE",
    "RESEARCH": "INTERMEDIATE",
    "ELITE": "INTERMEDIATE",
    "ELITE_LEGACY": "INTERMEDIATE",
    "PROFESSIONAL": "PRO",
    "PRO": "PRO",
    "ENTERPRISE": "ENTERPRISE",
}

ENTITLEMENT_SOURCES = frozenset({"SYSTEM_DEFAULT", "MANUAL_ALPHA", "TEST_FIXTURE", "BILLING_PROVIDER"})
FUTURE_BILLING_SOURCE = "BILLING_PROVIDER"

BEGINNER_CAPABILITIES = frozenset(
    {
        "MARKET_OVERVIEW",
        "MARKET_STATUS_DELAYED",
        "TOP_OPPORTUNITY_PREVIEW",
        "DATA_TRUST_BASIC",
        "WATCHLIST",
    }
)
INTERMEDIATE_CAPABILITIES = BEGINNER_CAPABILITIES | frozenset(
    {
        "DECISION_REASON_SUMMARY",
        "SUPPORTING_EVIDENCE",
        "CONTRADICTING_EVIDENCE",
        "SCANNER_FULL",
        "MARKET_STATUS_REALTIME",
    }
)
PRO_CAPABILITIES = INTERMEDIATE_CAPABILITIES | frozenset(
    {
        "AI_MARKET_ANALYST",
        "TOP_OPPORTUNITY_FULL",
        "DECISION_DIRECTION",
        "INVALIDATION",
        "RISK_EXPLANATION",
        "SHADOW_OUTCOME_SUMMARY",
        "DATA_TRUST_DETAILED",
    }
)
ENTERPRISE_CAPABILITIES = PRO_CAPABILITIES | frozenset(
    {
        "READONLY_API",
        "REPORT_EXPORT",
        "ORG_DASHBOARD",
        "ORG_ROLES",
        "TEAM_WATCHLIST",
        "TEAM_ALERTS",
        "SLA",
    }
)

PLAN_CAPABILITIES = {
    "BEGINNER": BEGINNER_CAPABILITIES,
    "INTERMEDIATE": INTERMEDIATE_CAPABILITIES,
    "PRO": PRO_CAPABILITIES,
    "ENTERPRISE": ENTERPRISE_CAPABILITIES,
}

FORBIDDEN_MEMBER_CAPABILITIES = frozenset(
    {
        "TRADE",
        "ORDER",
        "COPY_TRADE",
        "EXCHANGE_CONNECT",
        "EXCHANGE_WRITE",
        "WALLET_CONNECT",
        "POSITION_CONTROL",
        "LEVERAGE_CONTROL",
        "RISK_OVERRIDE",
        "STRATEGY_DEPLOY",
        "LESSON_ACTIVATE",
        "FOUNDER_OPERATOR",
        "FOUNDER_DIAGNOSTICS",
        "FOUNDER_LIVE_OPS",
        "CERTIFIED_RUNTIME_START",
        "CERTIFIED_SHORT_START",
        "RUNTIMELEASE_START",
        "SIX_HOUR_RUNTIME_START",
        "TWELVE_HOUR_RUNTIME_START",
        "BYBIT_AUTHENTICATED_WRITE",
        "BINANCE_AUTHENTICATED_WRITE",
    }
)


@dataclass(frozen=True, slots=True)
class MemberIdentity:
    user_id: str
    email: str
    account_status: str
    role: str
    plan: str
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class EntitlementSnapshot:
    user_id: str
    plan: str
    features: tuple[str, ...]
    source: str
    effective_at: str
    expires_at: str | None = None


def utc_effective_at() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_account_status(raw: str | None) -> str:
    if raw in ACTIVE_ACCOUNT_STATUSES:
        return "ACTIVE"
    if raw in DISABLED_ACCOUNT_STATUSES:
        return "DISABLED"
    if raw in PENDING_ACCOUNT_STATUSES:
        return "PENDING_VERIFICATION"
    return "DISABLED"


def account_can_use_member_api(raw_status: str | None) -> bool:
    return normalize_account_status(raw_status) == "ACTIVE"


def normalize_member_role(role_ids: Iterable[str]) -> str:
    ids = set(role_ids)
    if ids & FOUNDER_ROLE_IDS:
        return "FOUNDER_ADMIN"
    if ids & MEMBER_ROLE_IDS:
        return "MEMBER"
    return "MEMBER"


def normalize_plan(raw: str | None) -> str | None:
    if not raw:
        return None
    return LEGACY_PLAN_ALIASES.get(str(raw).strip().upper())


def highest_plan(product_codes: Iterable[str]) -> tuple[str, str]:
    best = "BEGINNER"
    source = "SYSTEM_DEFAULT"
    for code in product_codes:
        normalized = normalize_plan(code)
        if not normalized:
            continue
        source = "MANUAL_ALPHA"
        if PLAN_PRIORITY[normalized] > PLAN_PRIORITY[best]:
            best = normalized
    return best, source


def feature_allowed(plan: str | None, capability_id: str | None) -> bool:
    if not plan or not capability_id:
        return False
    normalized = normalize_plan(plan)
    if not normalized:
        return False
    capability = str(capability_id).strip().upper()
    if capability in FORBIDDEN_MEMBER_CAPABILITIES:
        return False
    return capability in PLAN_CAPABILITIES.get(normalized, frozenset())


def build_entitlement_snapshot(
    user_id: str,
    product_codes: Iterable[str],
    *,
    effective_at: str | None = None,
    expires_at: str | None = None,
) -> EntitlementSnapshot:
    plan, source = highest_plan(product_codes)
    return EntitlementSnapshot(
        user_id=user_id,
        plan=plan,
        features=tuple(sorted(PLAN_CAPABILITIES[plan])),
        source=source,
        effective_at=effective_at or utc_effective_at(),
        expires_at=expires_at,
    )
