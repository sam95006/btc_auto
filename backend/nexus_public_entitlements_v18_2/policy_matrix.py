"""Policy-configured plan matrix (server authority — not UI hardcoding)."""
from __future__ import annotations

from backend.nexus_public_entitlements_v18_2.capability_registry import READ_ONLY_CAPABILITIES
from backend.nexus_public_entitlements_v18_2.constants import MEMBERSHIP_PLANS, POLICY_VERSION

_PRO_CAPS = frozenset(
    {
        "MARKET_OVERVIEW",
        "MARKET_STATUS_REALTIME",
        "TOP_OPPORTUNITY_FULL",
        "SCANNER_FULL",
        "DECISION_DIRECTION",
        "DECISION_REASON_SUMMARY",
        "SUPPORTING_EVIDENCE",
        "CONTRADICTING_EVIDENCE",
        "INVALIDATION",
        "RISK_EXPLANATION",
        "DATA_TRUST_BASIC",
        "DATA_TRUST_DETAILED",
        "REGIME_BASIC",
        "FUNDING_SUMMARY",
        "OI_SUMMARY",
        "LIQUIDATION_SUMMARY",
        "WATCHLIST",
        "CUSTOM_ALERTS",
        "AI_MARKET_ANALYST",
        "SHADOW_OUTCOME_SUMMARY",
    }
)

_RESEARCH_EXTRA = frozenset(
    {
        "REGIME_PROBABILITY",
        "FUNDING_HISTORY",
        "OI_HISTORY",
        "ORDER_FLOW",
        "SPREAD_DEPTH",
        "CROSS_EXCHANGE_COMPARE",
        "HISTORICAL_SIMILARITY",
        "DECISION_TIMELINE",
        "SHADOW_OUTCOME_HISTORY",
        "PROCESS_CLASSIFICATION",
        "COUNTERFACTUAL_SUMMARY",
        "AI_RESEARCH",
        "CSV_EXPORT",
        "REPORT_EXPORT",
        "READONLY_API",
        "SCANNER_ADVANCED_FILTERS",
    }
)

_ENTERPRISE_ORG = frozenset(
    {
        "ORG_DASHBOARD",
        "ORG_ROLES",
        "TEAM_WATCHLIST",
        "TEAM_ALERTS",
        "WEBHOOK",
        "AUDIT_LOG",
        "SSO",
        "IP_ALLOWLIST",
        "SLA",
        "WHITE_LABEL_REPORT",
        "REPORT_EXPORT",
        "READONLY_API",
    }
)

PLAN_CAPABILITIES: dict[str, frozenset[str]] = {
    "VISITOR": frozenset(
        {
            "MARKET_OVERVIEW",
            "MARKET_STATUS_DELAYED",
            "TOP_OPPORTUNITY_PREVIEW",
        }
    ),
    "FREE": frozenset(
        {
            "MARKET_OVERVIEW",
            "MARKET_STATUS_DELAYED",
            "DATA_TRUST_BASIC",
            "TOP_OPPORTUNITY_PREVIEW",
            "SCANNER_PREVIEW",
            "WATCHLIST",
            "CUSTOM_ALERTS",
            "AI_BASIC",
            "DECISION_REASON_SUMMARY",
        }
    ),
    "PRO": _PRO_CAPS,
    "RESEARCH": _PRO_CAPS | _RESEARCH_EXTRA,
    "ENTERPRISE": _PRO_CAPS | _RESEARCH_EXTRA | _ENTERPRISE_ORG,
}

PLAN_LIMITS: dict[str, dict[str, int | str | None]] = {
    "VISITOR": {
        "top_opportunity_preview_max": 1,
        "watchlist_max": 0,
        "alerts_max": 0,
        "ai_questions_per_day": 0,
        "scanner_rows_max": 0,
    },
    "FREE": {
        "top_opportunity_preview_max": 3,
        "watchlist_max": 5,
        "alerts_max": 3,
        "ai_questions_per_day": 5,
        "scanner_rows_max": 10,
    },
    "PRO": {
        "top_opportunity_preview_max": 50,
        "watchlist_max": 100,
        "alerts_max": 50,
        "ai_questions_per_day": 100,
        "scanner_rows_max": 500,
    },
    "RESEARCH": {
        "top_opportunity_preview_max": 200,
        "watchlist_max": 500,
        "alerts_max": 200,
        "ai_questions_per_day": 500,
        "scanner_rows_max": 2000,
        "readonly_api_requests_per_day": 10000,
        "history_retention_days": 365,
    },
    "ENTERPRISE": {
        "top_opportunity_preview_max": 500,
        "watchlist_max": 5000,
        "alerts_max": 5000,
        "ai_questions_per_day": 5000,
        "scanner_rows_max": 10000,
        "readonly_api_requests_per_day": 100000,
        "history_retention_days": 730,
        "org_seats_max": 500,
    },
}


def assert_policy_integrity() -> None:
    for plan in MEMBERSHIP_PLANS:
        if plan not in PLAN_CAPABILITIES:
            raise RuntimeError(f"policy missing plan {plan}")
        if plan not in PLAN_LIMITS:
            raise RuntimeError(f"policy limits missing plan {plan}")
    allowed = frozenset(READ_ONLY_CAPABILITIES)
    for plan, caps in PLAN_CAPABILITIES.items():
        unknown = caps - allowed
        if unknown:
            raise RuntimeError(f"plan {plan} references unknown capabilities: {sorted(unknown)}")


assert_policy_integrity()


def policy_snapshot() -> dict:
    return {
        "policy_version": POLICY_VERSION,
        "plans": list(MEMBERSHIP_PLANS),
        "capabilities_by_plan": {p: sorted(PLAN_CAPABILITIES[p]) for p in MEMBERSHIP_PLANS},
        "limits_by_plan": PLAN_LIMITS,
    }
