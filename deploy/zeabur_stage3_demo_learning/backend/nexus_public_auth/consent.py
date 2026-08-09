"""Consent state machine for the public identity realm."""
from __future__ import annotations

from typing import Any

from backend.nexus_public_auth.constants import CONSENT_PURPOSES
from backend.nexus_public_auth.hard_bans import HardBanViolation
from backend.nexus_public_auth.store import PublicAuthStore, _utcnow


class ConsentService:
    def __init__(self, store: PublicAuthStore):
        self.store = store

    def set_consent(
        self,
        account_id: str,
        purpose: str,
        *,
        granted: bool,
        version: str = "v1",
        source: str = "member_self_service",
    ) -> dict[str, Any]:
        if purpose not in CONSENT_PURPOSES:
            raise HardBanViolation(f"unknown consent purpose: {purpose}")
        account = self.store.get_account(account_id)
        if account is None:
            raise HardBanViolation("account not found")
        record = {
            "purpose": purpose,
            "granted": bool(granted),
            "version": version,
            "source": source,
            "updated_at": _utcnow(),
        }
        account.consent[purpose] = record
        self.store.update_account(account)
        self.store.append_audit(
            "consent.update",
            "ALLOW",
            account_id=account_id,
            metadata=record,
        )
        return dict(record)

    def get_consent(self, account_id: str) -> dict[str, Any]:
        account = self.store.get_account(account_id)
        if account is None:
            raise HardBanViolation("account not found")
        # Ensure all known purposes appear (default denied).
        out: dict[str, Any] = {}
        for purpose in sorted(CONSENT_PURPOSES):
            out[purpose] = account.consent.get(
                purpose,
                {
                    "purpose": purpose,
                    "granted": False,
                    "version": None,
                    "source": None,
                    "updated_at": None,
                },
            )
        return out

    def require_consent(self, account_id: str, purpose: str) -> None:
        state = self.get_consent(account_id).get(purpose) or {}
        if not state.get("granted"):
            raise HardBanViolation(f"consent required: {purpose}")
