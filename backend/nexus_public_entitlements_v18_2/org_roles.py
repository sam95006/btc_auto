"""Enterprise organization roles — no Founder secrets."""
from __future__ import annotations

from backend.nexus_public_entitlements_v18_2.constants import ORG_ROLES

ORG_ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "ORG_ADMIN": frozenset(
        {
            "ORG_DASHBOARD",
            "ORG_ROLES",
            "TEAM_WATCHLIST",
            "TEAM_ALERTS",
            "AUDIT_LOG",
            "SSO",
            "IP_ALLOWLIST",
            "READONLY_API",
        }
    ),
    "ANALYST": frozenset(
        {
            "ORG_DASHBOARD",
            "TEAM_WATCHLIST",
            "TEAM_ALERTS",
            "REPORT_EXPORT",
            "AI_RESEARCH",
            "CSV_EXPORT",
        }
    ),
    "VIEWER": frozenset(
        {
            "ORG_DASHBOARD",
            "CUSTOM_ALERTS",
            "REPORT_EXPORT",
        }
    ),
}

FORBIDDEN_ORG_EXPOSURE = frozenset(
    {
        "founder_capital",
        "founder_portfolio",
        "order_id",
        "api_key",
        "exact_leverage",
        "private_strategy_params",
        "exchange_write",
    }
)


def org_role_has_capability(role: str, capability_id: str) -> bool:
    if role not in ORG_ROLES:
        return False
    return capability_id in ORG_ROLE_CAPABILITIES.get(role, frozenset())


def org_roles_snapshot() -> dict:
    return {
        "roles": list(ORG_ROLES),
        "capabilities_by_role": {r: sorted(ORG_ROLE_CAPABILITIES[r]) for r in ORG_ROLES},
        "forbidden_exposure": sorted(FORBIDDEN_ORG_EXPOSURE),
    }
