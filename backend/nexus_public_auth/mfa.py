"""MFA-ready abstraction for the public identity realm (no live provider).

Provides enrollment / challenge / verify hooks that are provider-agnostic.
TOTP/WebAuthn/email OTP are factor *types* only — no SMS gateway, no live
authenticator enrollment against production IdP.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.nexus_public_auth.constants import MFA_FACTOR_TYPES, MFA_STATUS_VALUES
from backend.nexus_public_auth.hard_bans import HardBanViolation
from backend.nexus_public_auth.store import PublicAuthStore, _new_id, _utcnow


@dataclass
class MfaFactor:
    factor_id: str
    account_id: str
    factor_type: str
    label: str
    status: str = "pending_enrollment"
    created_at: str = field(default_factory=_utcnow)
    verified_at: Optional[str] = None
    # Non-production stub secret fingerprint (never a live provider credential).
    secret_fingerprint: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MfaChallenge:
    challenge_id: str
    account_id: str
    factor_id: str
    factor_type: str
    created_at: str = field(default_factory=_utcnow)
    expires_at: str = ""
    consumed: bool = False
    # Stub challenge nonce — verify against local HMAC, not a live IdP.
    nonce: str = ""


class MfaService:
    """Provider-agnostic MFA facade for public member accounts."""

    def __init__(self, store: PublicAuthStore):
        self.store = store

    def enroll_factor(
        self,
        account_id: str,
        factor_type: str,
        *,
        label: str = "",
    ) -> dict[str, Any]:
        if factor_type not in MFA_FACTOR_TYPES:
            raise HardBanViolation(f"unsupported MFA factor type: {factor_type}")
        account = self.store.get_account(account_id)
        if account is None:
            raise HardBanViolation("account not found")
        if account.status != "active":
            raise HardBanViolation(f"account status {account.status} cannot enroll MFA")

        stub_secret = secrets.token_urlsafe(32)
        fingerprint = hashlib.sha256(stub_secret.encode("utf-8")).hexdigest()[:24]
        factor = MfaFactor(
            factor_id=_new_id("mfa"),
            account_id=account_id,
            factor_type=factor_type,
            label=label or f"{factor_type}-primary",
            status="pending_enrollment",
            secret_fingerprint=fingerprint,
            metadata={
                "provider": "NONE_NON_PRODUCTION",
                "enrollment_mode": "abstraction_stub",
                # Returned once for local verify_stub; not persisted as raw secret.
                "enrollment_secret_once": stub_secret,
            },
        )
        self.store.put_mfa_factor(factor)
        self.store.append_audit(
            "mfa.enroll_started",
            "ALLOW",
            account_id=account_id,
            metadata={
                "factor_id": factor.factor_id,
                "factor_type": factor_type,
                "status": factor.status,
            },
        )
        return {
            "factor_id": factor.factor_id,
            "factor_type": factor.factor_type,
            "label": factor.label,
            "status": factor.status,
            "enrollment_secret_once": stub_secret,
            "provider": "NONE_NON_PRODUCTION",
            "mfa_ready": True,
        }

    def confirm_enrollment(
        self,
        account_id: str,
        factor_id: str,
        *,
        enrollment_secret: str,
    ) -> dict[str, Any]:
        factor = self.store.get_mfa_factor(factor_id)
        if factor is None or factor.account_id != account_id:
            raise HardBanViolation("MFA factor not found")
        if factor.status not in MFA_STATUS_VALUES:
            raise HardBanViolation(f"invalid MFA status: {factor.status}")
        expected = hashlib.sha256(enrollment_secret.encode("utf-8")).hexdigest()[:24]
        if not hmac.compare_digest(expected, factor.secret_fingerprint):
            raise HardBanViolation("MFA enrollment confirmation failed")
        factor.status = "enabled"
        factor.verified_at = _utcnow()
        factor.metadata.pop("enrollment_secret_once", None)
        self.store.put_mfa_factor(factor)
        self.store.append_audit(
            "mfa.enroll_confirmed",
            "ALLOW",
            account_id=account_id,
            metadata={"factor_id": factor_id, "factor_type": factor.factor_type},
        )
        return {
            "factor_id": factor.factor_id,
            "status": factor.status,
            "verified_at": factor.verified_at,
            "mfa_ready": True,
        }

    def create_challenge(self, account_id: str, factor_id: str) -> dict[str, Any]:
        factor = self.store.get_mfa_factor(factor_id)
        if factor is None or factor.account_id != account_id:
            raise HardBanViolation("MFA factor not found")
        if factor.status != "enabled":
            raise HardBanViolation("MFA factor not enabled")
        nonce = secrets.token_urlsafe(24)
        challenge = MfaChallenge(
            challenge_id=_new_id("mfachal"),
            account_id=account_id,
            factor_id=factor_id,
            factor_type=factor.factor_type,
            nonce=nonce,
            expires_at=_utcnow(),  # stub; consumption check is primary gate
        )
        self.store.put_mfa_challenge(challenge)
        self.store.append_audit(
            "mfa.challenge_created",
            "ALLOW",
            account_id=account_id,
            metadata={"challenge_id": challenge.challenge_id, "factor_id": factor_id},
        )
        return {
            "challenge_id": challenge.challenge_id,
            "factor_type": factor.factor_type,
            "provider": "NONE_NON_PRODUCTION",
            "mfa_ready": True,
            # Stub response code derived from nonce+fingerprint for local verify.
            "stub_response_hint": self._stub_response(factor.secret_fingerprint, nonce),
        }

    def verify_challenge(
        self,
        account_id: str,
        challenge_id: str,
        *,
        response_code: str,
    ) -> dict[str, Any]:
        challenge = self.store.get_mfa_challenge(challenge_id)
        if challenge is None or challenge.account_id != account_id:
            raise HardBanViolation("MFA challenge not found")
        if challenge.consumed:
            raise HardBanViolation("MFA challenge already consumed")
        factor = self.store.get_mfa_factor(challenge.factor_id)
        if factor is None or factor.status != "enabled":
            raise HardBanViolation("MFA factor not enabled")
        expected = self._stub_response(factor.secret_fingerprint, challenge.nonce)
        if not hmac.compare_digest(expected, response_code):
            self.store.append_audit(
                "mfa.challenge_failed",
                "DENY",
                account_id=account_id,
                metadata={"challenge_id": challenge_id},
            )
            raise HardBanViolation("MFA challenge verification failed")
        challenge.consumed = True
        self.store.put_mfa_challenge(challenge)
        self.store.append_audit(
            "mfa.challenge_verified",
            "ALLOW",
            account_id=account_id,
            metadata={"challenge_id": challenge_id, "factor_id": factor.factor_id},
        )
        return {
            "verified": True,
            "challenge_id": challenge_id,
            "factor_id": factor.factor_id,
            "factor_type": factor.factor_type,
            "mfa_ready": True,
        }

    def list_factors(self, account_id: str) -> list[dict[str, Any]]:
        factors = self.store.list_mfa_factors(account_id)
        return [
            {
                "factor_id": f.factor_id,
                "factor_type": f.factor_type,
                "label": f.label,
                "status": f.status,
                "verified_at": f.verified_at,
                "created_at": f.created_at,
            }
            for f in factors
        ]

    def mfa_status(self, account_id: str) -> dict[str, Any]:
        factors = self.list_factors(account_id)
        enabled = [f for f in factors if f["status"] == "enabled"]
        return {
            "account_id": account_id,
            "mfa_ready": True,
            "enabled_factor_count": len(enabled),
            "factor_count": len(factors),
            "status": "enabled" if enabled else ("pending_enrollment" if factors else "disabled"),
            "supported_factor_types": sorted(MFA_FACTOR_TYPES),
            "provider": "NONE_NON_PRODUCTION",
        }

    @staticmethod
    def _stub_response(fingerprint: str, nonce: str) -> str:
        raw = f"{fingerprint}:{nonce}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:32]
