"""Public member session lifecycle with revocation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from backend.nexus_public_auth.constants import PUBLIC_IDENTITY_REALM, PUBLIC_JWT_ISSUER
from backend.nexus_public_auth.hard_bans import (
    HardBanViolation,
    refuse_private_admin_session_reuse,
    validate_public_issuer,
    validate_public_realm,
)
from backend.nexus_public_auth.jwt_issuer import PublicJwtIssuer
from backend.nexus_public_auth.roles import normalize_member_roles
from backend.nexus_public_auth.store import PublicAuthStore, PublicSession, _new_id, _utcnow


class SessionService:
    def __init__(self, store: PublicAuthStore, issuer: Optional[PublicJwtIssuer] = None):
        self.store = store
        self.issuer = issuer or PublicJwtIssuer()

    def create_session(
        self,
        account_id: str,
        *,
        tier: str,
        member_roles: list[str],
        ttl_seconds: int = 3600,
        mfa_challenge_id: Optional[str] = None,
        require_mfa: bool = False,
    ) -> dict[str, Any]:
        account = self.store.get_account(account_id)
        if account is None:
            raise HardBanViolation("account not found")
        if account.status != "active":
            raise HardBanViolation(f"account status {account.status} cannot create session")
        roles = normalize_member_roles(member_roles or account.member_roles)

        enabled_factors = [
            f
            for f in self.store.list_mfa_factors(account_id)
            if getattr(f, "status", None) == "enabled"
        ]
        mfa_required = bool(require_mfa) or bool(enabled_factors)
        mfa_verified = False
        if mfa_required:
            if not mfa_challenge_id:
                raise HardBanViolation(
                    "MFA challenge required before session create (mfa-ready policy)"
                )
            challenge = self.store.get_mfa_challenge(mfa_challenge_id)
            if challenge is None or challenge.account_id != account_id:
                raise HardBanViolation("MFA challenge not found for session create")
            if not challenge.consumed:
                raise HardBanViolation(
                    "MFA challenge must be verified before session create"
                )
            mfa_verified = True

        issued = self.issuer.issue(
            account_id=account_id,
            tier=tier or account.tier,
            member_roles=roles,
            ttl_seconds=ttl_seconds,
            extra_claims={"mfa_verified": mfa_verified} if mfa_verified else None,
        )
        validate_public_issuer(issued["issuer"])
        validate_public_realm(issued["realm"])
        # Adversarial: refuse if issued token somehow claims private execution.
        payload = self.issuer.verify(issued["token"])
        if payload.get("private_execution_access") is True:
            raise HardBanViolation(
                "HARD BAN: session token must never grant private execution access"
            )
        expires_at = datetime.fromtimestamp(
            issued["expires_at_epoch"], tz=timezone.utc
        ).isoformat()
        session = PublicSession(
            session_id=_new_id("sess"),
            account_id=account_id,
            token_jti=issued["jti"],
            issued_at=_utcnow(),
            expires_at=expires_at,
            realm=PUBLIC_IDENTITY_REALM,
            issuer=PUBLIC_JWT_ISSUER,
        )
        self.store.put_session(session)
        self.store.append_audit(
            "session.create",
            "ALLOW",
            account_id=account_id,
            metadata={
                "session_id": session.session_id,
                "jti": session.token_jti,
                "mfa_verified": mfa_verified,
            },
        )
        return {
            "session_id": session.session_id,
            "token": issued["token"],
            "jti": issued["jti"],
            "expires_at": expires_at,
            "realm": session.realm,
            "issuer": session.issuer,
            "mfa_verified": mfa_verified,
            "private_execution_access": False,
        }

    def revoke_session(self, session_id: str, *, reason: str = "user_revoke") -> dict[str, Any]:
        session = self.store.get_session(session_id)
        if session is None:
            raise HardBanViolation("session not found")
        session.revoked = True
        session.revoked_at = _utcnow()
        session.revoke_reason = reason
        self.store.put_session(session)
        self.store.append_audit(
            "session.revoke",
            "ALLOW",
            account_id=session.account_id,
            metadata={"session_id": session_id, "reason": reason},
        )
        return {
            "session_id": session_id,
            "revoked": True,
            "revoked_at": session.revoked_at,
            "reason": reason,
        }

    def revoke_all_for_account(self, account_id: str, *, reason: str = "account_wide") -> int:
        count = 0
        for sid, session in list(self.store.sessions.items()):
            if session.account_id == account_id and not session.revoked:
                self.revoke_session(sid, reason=reason)
                count += 1
        return count

    def authenticate(self, token: str) -> dict[str, Any]:
        payload = self.issuer.verify(token)
        if payload.get("token_use") != "public_member_session":
            refuse_private_admin_session_reuse()
        jti = str(payload["jti"])
        session = self.store.get_session_by_jti(jti)
        if session is None:
            raise HardBanViolation("session not registered")
        if session.revoked:
            raise HardBanViolation("session revoked")
        if session.realm != PUBLIC_IDENTITY_REALM or session.issuer != PUBLIC_JWT_ISSUER:
            refuse_private_admin_session_reuse()
        account = self.store.get_account(session.account_id)
        if account is None or account.status != "active":
            raise HardBanViolation("account not active")
        return {
            "account_id": account.account_id,
            "tier": account.tier,
            "member_roles": list(account.member_roles),
            "session_id": session.session_id,
            "jti": jti,
            "realm": session.realm,
            "issuer": session.issuer,
        }

    def reject_private_admin_token(self, token: str, *, claimed_issuer: str = "nexus-private") -> None:
        self.issuer.reject_foreign_token(token, claimed_issuer=claimed_issuer)
