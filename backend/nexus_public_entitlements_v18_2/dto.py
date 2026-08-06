"""Public DTO builders and navigation contract (server mirror for mobile)."""
from __future__ import annotations

from typing import Any

from backend.nexus_public_entitlements_v18_2.analytics_contract import analytics_contract_snapshot
from backend.nexus_public_entitlements_v18_2.constants import UI_DATA_STATES
from backend.nexus_public_entitlements_v18_2.org_roles import org_roles_snapshot


def navigation_contract_v18_2(*, include_organization: bool = False) -> dict[str, Any]:
    primary = [
        {"path": "/home", "label_zh": "總覽", "label_en": "Overview", "id": "overview"},
        {"path": "/scanner", "label_zh": "掃描器", "label_en": "Scanner", "id": "scanner"},
        {"path": "/alerts", "label_zh": "警報", "label_en": "Alerts", "id": "alerts"},
        {"path": "/intelligence", "label_zh": "情報", "label_en": "Intelligence", "id": "intelligence"},
    ]
    utility = [
        {"path": "/watchlist", "label_zh": "Watchlist", "label_en": "Watchlist", "id": "watchlist"},
        {"path": "/nex-ai", "label_zh": "AI", "label_en": "AI", "id": "ai"},
        {"path": "/account", "label_zh": "帳戶", "label_en": "Account", "id": "account"},
    ]
    org: list[dict[str, str]] = []
    if include_organization:
        org.append(
            {
                "path": "/organization",
                "label_zh": "Organization",
                "label_en": "Organization",
                "id": "organization",
            }
        )
    return {
        "schema": "member_navigation_contract_v18_2",
        "primary_nav": primary,
        "utility_nav": utility,
        "enterprise_nav": org,
        "forbidden_member_nav": ["/founder/operator", "/founder/live-ops", "/founder/diagnostics"],
        "modes": ["SIMPLE", "PRO"],
        "data_states": sorted(UI_DATA_STATES),
    }


def public_product_meta() -> dict[str, Any]:
    return {
        "ui_simplification_status": "PUBLIC_PRODUCT_ALPHA",
        "analytics": analytics_contract_snapshot(),
        "navigation": navigation_contract_v18_2(),
        "org_roles": org_roles_snapshot(),
    }
