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
    return _navigation_contract_payload(
        primary=primary,
        include_organization=include_organization,
        schema="member_navigation_contract_v18_2",
        modes=("SIMPLE", "PRO"),
    )


def navigation_contract_v18_2_1(*, include_organization: bool = False) -> dict[str, Any]:
    """Actual Zeabur panel IA (V18.2.1) — /overview + /opportunities primary routes."""
    primary = [
        {"path": "/overview", "label_zh": "總覽", "label_en": "Overview", "id": "overview"},
        {"path": "/opportunities", "label_zh": "機會", "label_en": "Opportunities", "id": "opportunities"},
        {"path": "/scanner", "label_zh": "掃描器", "label_en": "Scanner", "id": "scanner"},
        {"path": "/alerts", "label_zh": "警報", "label_en": "Alerts", "id": "alerts"},
        {"path": "/intelligence", "label_zh": "情報", "label_en": "Intelligence", "id": "intelligence"},
    ]
    return _navigation_contract_payload(
        primary=primary,
        include_organization=include_organization,
        schema="member_navigation_contract_v18_2_1",
        modes=("SIMPLE", "EXPERT"),
        mobile_bottom=("overview", "opportunities", "alerts", "more"),
        ai_path="/assistant",
    )


def _navigation_contract_payload(
    *,
    primary: list[dict[str, str]],
    include_organization: bool,
    schema: str,
    modes: tuple[str, ...],
    mobile_bottom: tuple[str, ...] | None = None,
    ai_path: str = "/nex-ai",
) -> dict[str, Any]:
    utility = [
        {"path": "/watchlist", "label_zh": "Watchlist", "label_en": "Watchlist", "id": "watchlist"},
        {"path": ai_path, "label_zh": "AI", "label_en": "AI", "id": "ai"},
        {"path": "/account", "label_zh": "帳戶", "label_en": "Account", "id": "account"},
    ]
    org: list[dict[str, str]] = []
    if include_organization:
        org.append(
            {
                "path": "/organization",
                "label_zh": "組織",
                "label_en": "Organization",
                "id": "organization",
            }
        )
    body: dict[str, Any] = {
        "schema": schema,
        "primary_nav": primary,
        "utility_nav": utility,
        "enterprise_nav": org,
        "forbidden_member_nav": [
            "/founder/operator",
            "/founder/live-ops",
            "/founder/diagnostics",
            "/founder/runtime",
        ],
        "modes": list(modes),
        "density_labels_zh": {"SIMPLE": "簡潔模式", "EXPERT": "專業模式"},
        "data_states": sorted(UI_DATA_STATES),
    }
    if schema == "member_navigation_contract_v18_2_1":
        body["feature_flag"] = "member_surface_v18_2_1"
    if mobile_bottom:
        body["mobile_bottom_nav"] = list(mobile_bottom)
    return body


def public_product_meta() -> dict[str, Any]:
    return {
        "ui_simplification_status": "PUBLIC_PRODUCT_ALPHA",
        "analytics": analytics_contract_snapshot(),
        "navigation": navigation_contract_v18_2(),
        "org_roles": org_roles_snapshot(),
    }
