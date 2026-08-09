"""Closed-beta invite lifecycle + server-authoritative member access."""
from __future__ import annotations

import os
import time
from typing import Any, Optional

from backend.nexus_closed_beta.constants import (
    ADMIN_INVITE_KEY_ENV,
    CLOSED_BETA_ENFORCED,
    DEFAULT_INVITE_TTL_SECONDS,
    DEFAULT_STAGING_ADMIN_KEY,
    MARKER,
    MEMBER_EXECUTION,
    PACKAGE,
    PRODUCTION_BILLING,
    READY_FOR_FOUNDER_VISUAL_REVIEW,
    SCHEMA,
)
from backend.nexus_closed_beta.store import (
    ClosedBetaStore,
    MemberBetaAccess,
    get_closed_beta_store,
)


class ClosedBetaError(Exception):
    pass


def _admin_key_ok(provided: Optional[str]) -> bool:
    expected = os.environ.get(ADMIN_INVITE_KEY_ENV) or DEFAULT_STAGING_ADMIN_KEY
    return bool(provided) and secrets_compare(str(provided), str(expected))


def secrets_compare(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


class ClosedBetaService:
    def __init__(self, store: Optional[ClosedBetaStore] = None) -> None:
        self.store = store or get_closed_beta_store()

    def foundation_status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "package": PACKAGE,
            "schema": SCHEMA,
            "marker": MARKER,
            "closed_beta_enforced": CLOSED_BETA_ENFORCED,
            "production_billing": PRODUCTION_BILLING,
            "member_execution": MEMBER_EXECUTION,
            "fake_paid_subscriptions": False,
            "statuses": sorted(["INVITED", "ACTIVE", "REVOKED", "EXPIRED"]),
            "invite_statuses": sorted(["PENDING", "REDEEMED", "REVOKED", "EXPIRED"]),
            "visual_status": READY_FOR_FOUNDER_VISUAL_REVIEW,
            "HUMAN_PRODUCT_VISUAL_PASS": "NOT_DECLARED_FOUNDER_ONLY",
        }

    def _expire_invite_if_needed(self, invite) -> Any:
        if invite.status == "PENDING" and float(invite.expires_at_epoch) <= time.time():
            invite.status = "EXPIRED"
            self.store.put_invite(invite)
            self.store.append_audit(
                "invite.expire",
                "ALLOW",
                actor="system",
                invite_id=invite.invite_id,
            )
        return invite

    def create_invite(
        self,
        *,
        admin_key: str,
        email_hint: Optional[str] = None,
        ttl_seconds: int = DEFAULT_INVITE_TTL_SECONDS,
        actor: str = "founder_admin",
    ) -> dict[str, Any]:
        if not _admin_key_ok(admin_key):
            self.store.append_audit("invite.create", "DENY", actor=actor or "unknown")
            raise ClosedBetaError("admin_key_invalid")
        invite, raw_code = self.store.create_invite(
            email_hint=email_hint,
            ttl_seconds=ttl_seconds,
            created_by=actor,
        )
        return {
            "ok": True,
            "invite": {
                "invite_id": invite.invite_id,
                "status": invite.status,
                "email_hint": invite.email_hint,
                "code_hint": invite.code_hint,
                "expires_at_epoch": invite.expires_at_epoch,
                "created_at": invite.created_at,
                "created_by": invite.created_by,
            },
            # Single-use staging inline delivery — never a production partner token.
            "invite_code": raw_code,
            "delivery": "inline_staging_token",
            "production_billing": False,
        }

    def redeem_invite(self, *, account_id: str, invite_code: str) -> dict[str, Any]:
        if not account_id:
            raise ClosedBetaError("account_required")
        invite = self.store.find_by_code(invite_code)
        if invite is None:
            self.store.append_audit(
                "invite.redeem",
                "DENY",
                actor=account_id,
                account_id=account_id,
                metadata={"reason": "not_found"},
            )
            raise ClosedBetaError("invite_not_found")
        invite = self._expire_invite_if_needed(invite)
        if invite.status == "EXPIRED":
            access = MemberBetaAccess(account_id=account_id, status="EXPIRED", invite_id=invite.invite_id)
            access.expired_at = access.updated_at
            self.store.put_access(access)
            raise ClosedBetaError("invite_expired")
        if invite.status == "REVOKED":
            access = MemberBetaAccess(account_id=account_id, status="REVOKED", invite_id=invite.invite_id)
            access.revoked_at = access.updated_at
            self.store.put_access(access)
            raise ClosedBetaError("invite_revoked")
        if invite.status == "REDEEMED":
            raise ClosedBetaError("invite_already_used")
        if invite.status != "PENDING":
            raise ClosedBetaError(f"invite_status_{invite.status}")

        invite.status = "REDEEMED"
        invite.redeemed_at = invite.created_at  # overwritten below
        from backend.nexus_closed_beta.store import _utcnow

        invite.redeemed_at = _utcnow()
        invite.redeemed_by_account_id = account_id
        self.store.put_invite(invite)

        access = MemberBetaAccess(
            account_id=account_id,
            status="ACTIVE",
            invite_id=invite.invite_id,
            activated_at=_utcnow(),
        )
        self.store.put_access(access)
        self.store.append_audit(
            "invite.redeem",
            "ALLOW",
            actor=account_id,
            invite_id=invite.invite_id,
            account_id=account_id,
        )
        self.store.append_audit(
            "member.activate",
            "ALLOW",
            actor=account_id,
            invite_id=invite.invite_id,
            account_id=account_id,
        )
        return {"ok": True, "beta_access": self.member_access_snapshot(account_id)}

    def revoke_invite(
        self,
        *,
        admin_key: str,
        invite_id: Optional[str] = None,
        account_id: Optional[str] = None,
        actor: str = "founder_admin",
    ) -> dict[str, Any]:
        if not _admin_key_ok(admin_key):
            raise ClosedBetaError("admin_key_invalid")
        if invite_id:
            invite = self.store.get_invite(invite_id)
            if invite is None:
                raise ClosedBetaError("invite_not_found")
            invite.status = "REVOKED"
            from backend.nexus_closed_beta.store import _utcnow

            invite.revoked_at = _utcnow()
            invite.revoked_by = actor
            self.store.put_invite(invite)
            if invite.redeemed_by_account_id:
                account_id = invite.redeemed_by_account_id
            self.store.append_audit(
                "invite.revoke",
                "ALLOW",
                actor=actor,
                invite_id=invite_id,
                account_id=account_id,
            )
        if account_id:
            access = self.store.get_access(account_id) or MemberBetaAccess(account_id=account_id)
            from backend.nexus_closed_beta.store import _utcnow

            access.status = "REVOKED"
            access.revoked_at = _utcnow()
            self.store.put_access(access)
            self.store.append_audit(
                "member.revoke",
                "ALLOW",
                actor=actor,
                account_id=account_id,
                invite_id=invite_id,
            )
        return {"ok": True, "revoked": True, "account_id": account_id, "invite_id": invite_id}

    def member_access_snapshot(self, account_id: str) -> dict[str, Any]:
        access = self.store.get_access(account_id)
        if access is None:
            return {
                "account_id": account_id,
                "status": "INVITED",
                "invite_id": None,
                "activated_at": None,
                "revoked_at": None,
                "expired_at": None,
                "entitlement_authority": "SERVER",
                "production_billing": False,
                "closed_beta_enforced": CLOSED_BETA_ENFORCED,
                "has_access": False if CLOSED_BETA_ENFORCED else True,
            }
        # Re-check invite expiry for pending/invited without activation.
        if access.invite_id:
            invite = self.store.get_invite(access.invite_id)
            if invite is not None:
                invite = self._expire_invite_if_needed(invite)
                if invite.status == "EXPIRED" and access.status in {"INVITED", "ACTIVE"}:
                    # Only expire non-activated; ACTIVE stays until revoke.
                    if access.status == "INVITED":
                        access.status = "EXPIRED"
                        from backend.nexus_closed_beta.store import _utcnow

                        access.expired_at = _utcnow()
                        self.store.put_access(access)
        status = access.status
        has_access = status == "ACTIVE"
        return {
            "account_id": account_id,
            "status": status,
            "invite_id": access.invite_id,
            "activated_at": access.activated_at,
            "revoked_at": access.revoked_at,
            "expired_at": access.expired_at,
            "entitlement_authority": "SERVER",
            "production_billing": False,
            "closed_beta_enforced": CLOSED_BETA_ENFORCED,
            "has_access": has_access,
            "updated_at": access.updated_at,
        }

    def require_active(self, account_id: str) -> dict[str, Any]:
        snap = self.member_access_snapshot(account_id)
        if CLOSED_BETA_ENFORCED and not snap.get("has_access"):
            raise ClosedBetaError(f"beta_access_{snap.get('status')}")
        return snap


_SVC: Optional[ClosedBetaService] = None


def get_closed_beta_service() -> ClosedBetaService:
    global _SVC
    if _SVC is None:
        _SVC = ClosedBetaService()
    return _SVC
