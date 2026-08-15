"""Entitlement alpha — resolves from verified session + DB, not client headers."""
from __future__ import annotations

from typing import Any

from backend.nexus_public_entitlements_v18_2.authority import (
    PublicEntitlementAuthority,
    normalize_plan,
)
from backend.nexus_product_backend.auth_alpha import AuthAlphaService
from backend.nexus_product_backend.repository import ProductRepository

PLAN_PRIORITY = ("VISITOR", "FREE", "PRO", "RESEARCH", "ENTERPRISE")


class EntitlementAlphaService:
    ALPHA_READY = "ENTITLEMENT_ALPHA_READY"

    def __init__(
        self,
        repo: ProductRepository,
        auth: AuthAlphaService,
        authority: PublicEntitlementAuthority | None = None,
    ):
        self.repo = repo
        self.auth = auth
        self.authority = authority or PublicEntitlementAuthority()

    def _resolve_plan(self, account_id: str) -> str:
        codes = self.repo.active_entitlements(account_id)
        if not codes:
            return "FREE"
        best = "VISITOR"
        for code in codes:
            normalized = normalize_plan(code)
            if PLAN_PRIORITY.index(normalized) > PLAN_PRIORITY.index(best):
                best = normalized
        return best

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
        plan = self._resolve_plan(session["account_id"])
        allowed = self.authority.has_capability(plan, capability_id, org_role=org_role)
        return {
            "allowed": allowed,
            "plan": plan,
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
            self.authority.require_capability("VISITOR", capability_id, org_role=org_role)
        return decision
