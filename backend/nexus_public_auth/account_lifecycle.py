"""Account deletion and data export for the public identity realm."""
from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any, Optional

from backend.nexus_public_auth.hard_bans import HardBanViolation
from backend.nexus_public_auth.sessions import SessionService
from backend.nexus_public_auth.store import PublicAuthStore, _utcnow


class AccountLifecycleService:
    def __init__(self, store: PublicAuthStore, sessions: Optional[SessionService] = None):
        self.store = store
        self.sessions = sessions or SessionService(store)

    def request_deletion(self, account_id: str, *, reason: str = "user_request") -> dict[str, Any]:
        account = self.store.get_account(account_id)
        if account is None:
            raise HardBanViolation("account not found")
        if account.status == "deleted":
            raise HardBanViolation("account already deleted")
        account.status = "deletion_pending"
        account.deletion_requested_at = _utcnow()
        self.store.update_account(account)
        revoked = self.sessions.revoke_all_for_account(account_id, reason="account_deletion")
        self.store.append_audit(
            "account.deletion_requested",
            "ALLOW",
            account_id=account_id,
            metadata={"reason": reason, "sessions_revoked": revoked},
        )
        return {
            "account_id": account_id,
            "status": account.status,
            "deletion_requested_at": account.deletion_requested_at,
            "sessions_revoked": revoked,
        }

    def finalize_deletion(self, account_id: str) -> dict[str, Any]:
        account = self.store.get_account(account_id)
        if account is None:
            raise HardBanViolation("account not found")
        if account.status not in {"deletion_pending", "active"}:
            raise HardBanViolation(f"cannot finalize deletion from status={account.status}")
        # Soft-delete retained metadata for audit; PII fields scrubbed.
        account.email = f"deleted+{account_id}@invalid.local"
        account.display_name = "DELETED"
        account.consent = {}
        account.status = "deleted"
        account.updated_at = _utcnow()
        self.store.update_account(account)
        self.sessions.revoke_all_for_account(account_id, reason="account_deleted")
        self.store.append_audit(
            "account.deleted",
            "ALLOW",
            account_id=account_id,
            metadata={"scrubbed": True},
        )
        return {"account_id": account_id, "status": "deleted"}

    def export_account_data(self, account_id: str) -> dict[str, Any]:
        account = self.store.get_account(account_id)
        if account is None:
            raise HardBanViolation("account not found")
        sessions = [
            {
                "session_id": s.session_id,
                "issued_at": s.issued_at,
                "expires_at": s.expires_at,
                "revoked": s.revoked,
                "revoked_at": s.revoked_at,
            }
            for s in self.store.sessions.values()
            if s.account_id == account_id
        ]
        export_id = f"export_{uuid.uuid4().hex[:16]}"
        payload = {
            "export_id": export_id,
            "exported_at": _utcnow(),
            "schema": "public_account_export_v1",
            "account": {
                "account_id": account.account_id,
                "email": account.email,
                "display_name": account.display_name,
                "tier": account.tier,
                "member_roles": list(account.member_roles),
                "org_roles": deepcopy(account.org_roles),
                "team_roles": deepcopy(account.team_roles),
                "status": account.status,
                "created_at": account.created_at,
                "updated_at": account.updated_at,
                "consent": deepcopy(account.consent),
            },
            "sessions": sessions,
            "audit": self.store.list_audit(account_id=account_id),
            "notes": [
                "NON_PRODUCTION export",
                "No private Lesson Memory",
                "No private checkpoint data",
                "No exchange credentials",
            ],
        }
        self.store.save_export(export_id, payload)
        self.store.append_audit(
            "account.data_export",
            "ALLOW",
            account_id=account_id,
            metadata={"export_id": export_id},
        )
        return payload
