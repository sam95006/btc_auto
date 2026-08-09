"""Billing readiness — verify entitlement can later accept billing→subscription→capability."""
from __future__ import annotations

from typing import Any


def billing_readiness() -> dict[str, Any]:
    """Do NOT activate Production Billing. Document hook points only."""
    entitlement_ok = False
    subscription_boundary_ok = False
    production_billing = False
    try:
        from backend.nexus_public_entitlements_v18_2.authority import (
            PUBLIC_ENTITLEMENT_AUTHORITY,
        )

        dto = PUBLIC_ENTITLEMENT_AUTHORITY.build_dto(
            plan="FREE",
            entitlement_source="policy_default",
        )
        entitlement_ok = dto.get("production_billing") is False and dto.get("authority_id")
        production_billing = bool(dto.get("production_billing"))
    except Exception as exc:
        return {
            "ok": False,
            "production_billing_activated": False,
            "error": str(exc),
            "future_path": [
                "billing_provider_event",
                "server_subscription_record",
                "PUBLIC_ENTITLEMENT_AUTHORITY.build_dto(entitlement_source=subscription)",
                "capability grant",
            ],
            "frontend_only_paid_authority": False,
        }

    try:
        from backend.nexus_public_subscription_boundary.service import (
            SubscriptionBoundaryService,
        )

        snap = SubscriptionBoundaryService().foundation_status()
        subscription_boundary_ok = snap.get("live_billing_enabled") is False
    except Exception:
        subscription_boundary_ok = False

    return {
        "ok": True,
        "production_billing_activated": False,
        "production_billing": production_billing,
        "entitlement_authority_ready_for_subscription_binding": bool(entitlement_ok),
        "subscription_boundary_present": subscription_boundary_ok,
        "frontend_only_paid_authority": False,
        "future_path": [
            "billing_provider_webhook (future)",
            "server_subscription_record",
            "entitlement_source=subscription",
            "capability grant via PUBLIC_ENTITLEMENT_AUTHORITY",
        ],
        "member_execution": 0,
    }
