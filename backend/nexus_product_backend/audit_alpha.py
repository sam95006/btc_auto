"""Immutable-style product audit alpha service."""
from __future__ import annotations

from typing import Any

from backend.nexus_product_backend.repository import ProductRepository


class ProductAuditAlphaService:
    ALPHA_READY = "AUDIT_ALPHA_READY"

    def __init__(self, repo: ProductRepository):
        self.repo = repo
        self._last_hash: str | None = None

    def record(
        self,
        *,
        actor_account_id: str | None,
        action: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        detail: dict[str, Any] | None = None,
        org_id: str | None = None,
    ) -> dict[str, Any]:
        event_id = self.repo.append_product_audit(
            actor_account_id=actor_account_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            org_id=org_id,
            prev_hash=self._last_hash,
        )
        rows = self.repo.pool.fetchall(
            "SELECT content_hash FROM nexus.product_audit_events WHERE event_id = %s",
            (event_id,),
        )
        content_hash = rows[0][0] if rows else None
        self._last_hash = content_hash
        return {
            "event_id": event_id,
            "content_hash": content_hash,
            "alpha_status": self.ALPHA_READY,
        }
