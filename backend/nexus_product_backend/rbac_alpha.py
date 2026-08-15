"""RBAC alpha evaluator backed by PostgreSQL bindings."""
from __future__ import annotations

from typing import Any

from backend.nexus_product_backend.auth_alpha import AuthAlphaService
from backend.nexus_product_backend.repository import ProductRepository


class RbacAlphaService:
    ALPHA_READY = "RBAC_ALPHA_READY"

    def __init__(self, repo: ProductRepository, auth: AuthAlphaService):
        self.repo = repo
        self.auth = auth

    def permissions_for_session(
        self,
        session_id: str,
        *,
        org_id: str | None = None,
    ) -> dict[str, Any]:
        session = self.auth.resolve_session(session_id)
        if not session:
            return {
                # JSON-serializable list for Flask jsonify / HTTP clients.
                "permissions": [],
                "allowed": False,
                "reason": "invalid_session",
                "alpha_status": self.ALPHA_READY,
            }
        perms = sorted(self.repo.role_permissions(session["account_id"], org_id=org_id))
        return {
            "permissions": perms,
            "allowed": True,
            "account_id": session["account_id"],
            "alpha_status": self.ALPHA_READY,
        }

    def require_permission(
        self,
        session_id: str,
        permission_code: str,
        *,
        org_id: str | None = None,
    ) -> None:
        result = self.permissions_for_session(session_id, org_id=org_id)
        if not result["allowed"]:
            raise PermissionError("invalid_session")
        if permission_code not in result["permissions"]:
            raise PermissionError(f"missing_permission:{permission_code}")
