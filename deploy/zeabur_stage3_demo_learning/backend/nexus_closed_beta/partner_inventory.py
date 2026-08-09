"""Partner Agent API inventory only — no external endpoint exposure."""
from __future__ import annotations

from typing import Any


def partner_api_inventory() -> dict[str, Any]:
    """
    Inventory existing public API boundaries and identify the future attach point:
    NEXUS Backend → Agent Gateway → Partner Agent API.

    No Partner Agent API is exposed externally in this release.
    """
    existing_public_api_prefixes = [
        "/api/public/auth",
        "/api/public/entitlements/v18_2",
        "/api/public/subscription",
        "/api/public/market-pulse",
        "/api/public/live-funnel",
        "/api/public/decision-product",
        "/api/public/decision-cloud",
        "/api/public/member-intel",
        "/api/public/live-data",
        "/api/public/runtime-snapshot",
        "/api/public/v1/realtime",
        "/api/public/v2/realtime",
        "/api/nexus/public/radar",
        "/api/nexus/public/retention",
        "/api/nexus/public/analytics",
        "/api/nexus/public/closed-beta",
    ]
    return {
        "new_external_agent_api_exposed": False,
        "partner_tokens_issued": False,
        "partner_architecture_hardcoded": False,
        "claude_credentials_exposed": False,
        "inventory_only": True,
        "existing_public_api_prefixes": existing_public_api_prefixes,
        "future_attach_point": {
            "path": "NEXUS Backend → Agent Gateway → Partner Agent API",
            "gateway_stub": "/api/nexus/internal/agent-gateway",
            "partner_api_stub": "/api/nexus/partner/agent",
            "status": "NOT_EXPOSED",
            "notes": [
                "Attach point reserved for future Partner Agent API.",
                "No production partner tokens in closed beta.",
                "Claude credentials must never surface on public routes.",
            ],
        },
    }
