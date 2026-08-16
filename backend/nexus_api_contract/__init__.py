"""Versioned public API contract definitions — safe read models only."""
from __future__ import annotations

from typing import Any

API_CONTRACT_VERSION = "v18_3_3_api_contract_v1"

PUBLIC_RESOURCES = {
    "health": {"methods": ["GET"], "auth": "none"},
    "readiness": {"methods": ["GET"], "auth": "none"},
    "capabilities": {"methods": ["GET"], "auth": "optional"},
}

AUTHENTICATED_RESOURCES = {
    "session": {"methods": ["GET", "DELETE"], "auth": "session"},
    "profile": {"methods": ["GET"], "auth": "session"},
    "memberships": {"methods": ["GET"], "auth": "session"},
}

ENTITLEMENT_REQUIRED_RESOURCES = {
    "shadow_watch_snapshot": {
        "methods": ["GET"],
        "auth": "session",
        "capability": "product.shadow.read",
    },
    "research_digest": {
        "methods": ["GET"],
        "auth": "session",
        "capability": "research.digest.read",
    },
}

INTERNAL_RESOURCES = {
    "migration_catalog": {"methods": ["GET"], "auth": "internal"},
    "backup_manifest": {"methods": ["GET"], "auth": "internal"},
}

EXCLUDED_RESOURCES = frozenset(
    {
        "exchange_credentials",
        "order_execution",
        "demo_trading",
        "mainnet_trading",
        "policy_mutation",
        "lesson_auto_apply",
    }
)


def contract_snapshot() -> dict[str, Any]:
    return {
        "schema": API_CONTRACT_VERSION,
        "public": PUBLIC_RESOURCES,
        "authenticated": AUTHENTICATED_RESOURCES,
        "entitlement_required": ENTITLEMENT_REQUIRED_RESOURCES,
        "internal": INTERNAL_RESOURCES,
        "excluded": sorted(EXCLUDED_RESOURCES),
        "execution_controls_mapped": False,
    }


def validate_contract() -> dict[str, Any]:
    errors: list[str] = []
    for name in EXCLUDED_RESOURCES:
        for bucket in (PUBLIC_RESOURCES, AUTHENTICATED_RESOURCES, ENTITLEMENT_REQUIRED_RESOURCES):
            if name in bucket:
                errors.append(f"excluded_resource_leaked:{name}")
    return {"ok": not errors, "errors": errors, "contract": contract_snapshot()}
