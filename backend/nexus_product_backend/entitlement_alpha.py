"""Entitlement alpha — resolves from verified session + DB, not client headers."""
from __future__ import annotations

from typing import Any

from backend.nexus_product_backend.member_foundation import (
    build_entitlement_snapshot,
    feature_allowed,
)
from backend.nexus_product_backend.auth_alpha import AuthAlphaService
from backend.nexus_product_backend.repository import ProductRepository


class EntitlementAlphaService:
    ALPHA_READY = "ENTITLEMENT_ALPHA_READY"

    def __init__(
        self,
        repo: ProductRepository,
        auth: AuthAlphaService,
    ):
        self.repo = repo
        self.auth = auth

    def _resolve_snapshot(self, account_id: str):
        codes = self.repo.active_entitlements(account_id)
        return build_entitlement_snapshot(account_id, codes)

    def _resolve_plan(self, account_id: str) -> str:
        return self._resolve_snapshot(account_id).plan

    def decision_from_session(
        self,
        session_id: str,
        capability_id: str,
        *,
        org_role: str | None = None,
    ) -> dict[str, Any]:
        session = self.auth.resolve_session(session_id)
        if not session:
            return {
                "allowed": False,
                "reason": "invalid_session",
                "plan": "VISITOR",
                "alpha_status": self.ALPHA_READY,
            }
        snapshot = self._resolve_snapshot(session["account_id"])
        allowed = feature_allowed(snapshot.plan, capability_id)
        return {
            "allowed": allowed,
            "plan": snapshot.plan,
            "entitlement_source": snapshot.source,
            "features": list(snapshot.features),
            "account_id": session["account_id"],
            "capability_id": capability_id,
            "alpha_status": self.ALPHA_READY,
        }

    def require_capability(
        self,
        session_id: str,
        capability_id: str,
        *,
        org_role: str | None = None,
    ) -> dict[str, Any]:
        decision = self.decision_from_session(session_id, capability_id, org_role=org_role)
        if not decision["allowed"]:
            raise PermissionError(f"entitlement_required:{capability_id}")
        return decision
