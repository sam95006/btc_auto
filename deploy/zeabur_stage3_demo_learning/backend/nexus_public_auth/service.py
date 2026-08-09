"""Facade service composing PUB2-F auth + PUB2-H org/privacy ACL hardening."""
from __future__ import annotations

from typing import Any, Optional

from backend.nexus_public_auth.account_lifecycle import AccountLifecycleService
from backend.nexus_public_auth.consent import ConsentService
from backend.nexus_public_auth.constants import (
    BRANCH,
    DEPLOYMENT_MODE,
    HARD_BANS,
    LANE,
    LOGIN_LOCKOUT_SECONDS,
    LOGIN_MAX_FAILURES,
    PACKAGE,
    PRIVATE_EXECUTION_FEATURE_DENYLIST,
    PUBLIC_IDENTITY_REALM,
    PUBLIC_JWT_ISSUER,
    SCHEMA,
)
from backend.nexus_public_auth.entitlements import (
    assert_valid_tier,
    assign_tier_manual,
    entitlement_snapshot,
    has_feature,
    require_feature,
)
from backend.nexus_public_auth.hard_bans import HardBanViolation, assert_env_hard_bans
from backend.nexus_public_auth.jwt_issuer import PublicJwtIssuer, get_default_issuer
from backend.nexus_public_auth.mfa import MfaService
from backend.nexus_public_auth.org_access import (
    SELF_REGISTER_ROLES,
    SELF_REGISTER_TIER,
    add_org_member,
    assign_org_roles_authorized,
    assign_team_roles_authorized,
    create_organization,
    require_self_or_admin,
)
from backend.nexus_public_auth.passwords import hash_password, verify_password
from backend.nexus_public_auth.rate_limit import AuthRateLimiter, get_default_rate_limiter
from backend.nexus_public_auth.roles import normalize_member_roles
from backend.nexus_public_auth.sessions import SessionService
from backend.nexus_public_auth.store import PublicAuthStore, get_default_store
from backend.nexus_public_auth.tokens import (
    RESET_TTL_SEC,
    VERIFY_TTL_SEC,
    AuthTokenStore,
    get_default_token_store,
)


class PublicAuthMembershipService:
    """Non-production public identity + entitlement + org security foundation."""

    def __init__(
        self,
        store: Optional[PublicAuthStore] = None,
        issuer: Optional[PublicJwtIssuer] = None,
        rate_limiter: Optional[AuthRateLimiter] = None,
        tokens: Optional[AuthTokenStore] = None,
    ):
        assert_env_hard_bans()
        self.store = store or get_default_store()
        self.issuer = issuer or get_default_issuer()
        self.rate_limiter = rate_limiter or get_default_rate_limiter()
        self.tokens = tokens or get_default_token_store()
        self.sessions = SessionService(self.store, self.issuer)
        self.consent = ConsentService(self.store)
        self.lifecycle = AccountLifecycleService(self.store, self.sessions)
        self.mfa = MfaService(self.store)

    def foundation_status(self) -> dict[str, Any]:
        return {
            "lane": LANE,
            "package": PACKAGE,
            "schema": SCHEMA,
            "branch": BRANCH,
            "deployment_mode": DEPLOYMENT_MODE,
            "public_identity_realm": PUBLIC_IDENTITY_REALM,
            "public_jwt_issuer": PUBLIC_JWT_ISSUER,
            "shared_jwt_issuer_count": 0,
            "live_billing_enabled": False,
            "production_customer_database": False,
            "private_execution_access_via_entitlement": False,
            "private_execution_feature_denylist": sorted(PRIVATE_EXECUTION_FEATURE_DENYLIST),
            "mfa_ready": True,
            "rate_limits": self.rate_limiter.snapshot(),
            "hard_bans": sorted(HARD_BANS),
            "store": self.store.snapshot(),
            "tokens": self.tokens.snapshot(),
            "issuer_fingerprint": self.issuer.fingerprint(),
            "password_credentials": True,
            "email_verification": True,
            "forgot_reset": True,
            "dev_token_return": True,
        }

    def register_member(
        self,
        email: str,
        display_name: str,
        *,
        tier: str = "Free",
        member_roles: Optional[list[str]] = None,
        rate_subject: Optional[str] = None,
        password: Optional[str] = None,
    ) -> dict[str, Any]:
        subject = (rate_subject or email or "anonymous").strip().lower() or "anonymous"
        self.rate_limiter.check("register", subject)
        # Self-registration is locked to Free + member (PUB2-H).
        requested_roles = list(member_roles or ["member"])
        if set(requested_roles) - SELF_REGISTER_ROLES:
            raise HardBanViolation(
                "HARD BAN: member privilege escalation blocked — "
                "self-registration may only assign role 'member'"
            )
        if tier != SELF_REGISTER_TIER:
            raise HardBanViolation(
                "HARD BAN: member privilege escalation blocked — "
                f"self-registration may only use tier {SELF_REGISTER_TIER!r}"
            )
        roles = normalize_member_roles(requested_roles)
        assert_valid_tier(tier)
        pwd_hash = None
        if password:
            try:
                pwd_hash = hash_password(password)
            except ValueError as exc:
                raise HardBanViolation(str(exc)) from exc
        account = self.store.create_account(
            email,
            display_name,
            tier=tier,
            password_hash=pwd_hash,
            email_verified=False,
        )
        account.member_roles = roles
        self.store.update_account(account)
        out: dict[str, Any] = {
            "account_id": account.account_id,
            "email": account.email,
            "tier": account.tier,
            "member_roles": roles,
            "realm": PUBLIC_IDENTITY_REALM,
            "email_verified": False,
            "password_set": bool(pwd_hash),
        }
        if pwd_hash:
            verify = self.tokens.issue(
                account_id=account.account_id,
                purpose="email_verify",
                ttl_seconds=VERIFY_TTL_SEC,
            )
            out["verification"] = {
                "token": verify["token"],
                "expires_at_epoch": verify["expires_at_epoch"],
                "delivery": "inline_staging_token",
            }
            try:
                from backend.nexus_product_analytics.events import record_event

                record_event("signup_completed", account_id=account.account_id)
            except Exception:
                pass
        self.store.append_audit(
            "account.register",
            "ALLOW",
            account_id=account.account_id,
            metadata={
                "tier": tier,
                "member_roles": roles,
                "email_verified": False,
                "password_set": bool(pwd_hash),
            },
        )
        return out

    def login_with_password(
        self,
        email: str,
        password: str,
        *,
        ttl_seconds: int = 3600,
    ) -> dict[str, Any]:
        subject = (email or "").strip().lower() or "anonymous"
        self.rate_limiter.check("login", subject)
        account = self.store.get_account_by_email(email)
        # Uniform failure — do not leak account existence beyond rate limits.
        def _fail(msg: str = "invalid email or password") -> None:
            raise HardBanViolation(msg)

        if account is None or not account.password_hash:
            _fail()
        import time as _time

        now = _time.time()
        if account.lockout_until_epoch and now < float(account.lockout_until_epoch):
            raise HardBanViolation("account temporarily locked — too many failed logins")
        if not verify_password(password, account.password_hash or ""):
            account.failed_login_count = int(account.failed_login_count or 0) + 1
            if account.failed_login_count >= LOGIN_MAX_FAILURES:
                account.lockout_until_epoch = now + float(LOGIN_LOCKOUT_SECONDS)
                account.failed_login_count = 0
            self.store.update_account(account)
            self.store.append_audit(
                "account.login",
                "DENY",
                account_id=account.account_id,
                metadata={"reason": "bad_password"},
            )
            _fail()
        account.failed_login_count = 0
        account.lockout_until_epoch = None
        self.store.update_account(account)
        session = self.create_session_rate_limited(
            account.account_id,
            tier=account.tier,
            member_roles=list(account.member_roles),
            ttl_seconds=ttl_seconds,
            require_mfa=False,
        )
        self.store.append_audit(
            "account.login",
            "ALLOW",
            account_id=account.account_id,
            metadata={"session_id": session["session_id"]},
        )
        try:
            from backend.nexus_product_analytics.events import record_event

            record_event("login_completed", account_id=account.account_id)
        except Exception:
            pass
        return {
            "account": {
                "account_id": account.account_id,
                "email": account.email,
                "display_name": account.display_name,
                "tier": account.tier,
                "email_verified": bool(account.email_verified),
                "member_roles": list(account.member_roles),
            },
            "session": session,
        }

    def logout(self, token: str) -> dict[str, Any]:
        auth = self.authenticate_rate_limited(token)
        result = self.sessions.revoke_session(
            str(auth["session_id"]), reason="user_logout"
        )
        return {"ok": True, "revoked": True, "result": result}

    def verify_email(self, raw_token: str) -> dict[str, Any]:
        self.rate_limiter.check("email_verify", (raw_token or "")[:16] or "anonymous")
        try:
            rec = self.tokens.consume(raw_token, purpose="email_verify")
        except ValueError as exc:
            raise HardBanViolation(str(exc)) from exc
        account = self.store.get_account(rec.account_id)
        if account is None:
            raise HardBanViolation("account not found")
        account.email_verified = True
        from backend.nexus_public_auth.store import _utcnow

        account.email_verified_at = _utcnow()
        self.store.update_account(account)
        self.store.append_audit(
            "account.email_verify",
            "ALLOW",
            account_id=account.account_id,
            metadata={"token_id": rec.token_id},
        )
        return {
            "account_id": account.account_id,
            "email": account.email,
            "email_verified": True,
            "email_verified_at": account.email_verified_at,
        }

    def request_email_verification(self, account_id: str) -> dict[str, Any]:
        self.rate_limiter.check("email_verify", account_id)
        account = self.store.get_account(account_id)
        if account is None:
            raise HardBanViolation("account not found")
        if account.email_verified:
            return {"email_verified": True, "resent": False}
        verify = self.tokens.issue(
            account_id=account.account_id,
            purpose="email_verify",
            ttl_seconds=VERIFY_TTL_SEC,
        )
        return {
            "email_verified": False,
            "resent": True,
            "verification": {
                "token": verify["token"],
                "expires_at_epoch": verify["expires_at_epoch"],
                "delivery": "inline_staging_token",
            },
        }

    def forgot_password(self, email: str) -> dict[str, Any]:
        subject = (email or "").strip().lower() or "anonymous"
        self.rate_limiter.check("forgot_password", subject)
        account = self.store.get_account_by_email(email)
        # Always return ok shape to avoid email enumeration; include token only if found.
        if account is None or not account.password_hash:
            return {
                "ok": True,
                "accepted": True,
                "delivery": "inline_staging_token",
                "reset": None,
                "note": "If the account exists, a reset token was issued.",
            }
        reset = self.tokens.issue(
            account_id=account.account_id,
            purpose="password_reset",
            ttl_seconds=RESET_TTL_SEC,
        )
        self.store.append_audit(
            "account.forgot_password",
            "ALLOW",
            account_id=account.account_id,
            metadata={"token_id": reset["token_id"]},
        )
        return {
            "ok": True,
            "accepted": True,
            "delivery": "inline_staging_token",
            "reset": {
                "token": reset["token"],
                "expires_at_epoch": reset["expires_at_epoch"],
            },
            "note": "One-time reset token issued (staging inline; no email vendor).",
        }

    def reset_password(self, raw_token: str, new_password: str) -> dict[str, Any]:
        self.rate_limiter.check("reset_password", (raw_token or "")[:16] or "anonymous")
        try:
            rec = self.tokens.consume(raw_token, purpose="password_reset")
        except ValueError as exc:
            raise HardBanViolation(str(exc)) from exc
        account = self.store.get_account(rec.account_id)
        if account is None:
            raise HardBanViolation("account not found")
        try:
            account.password_hash = hash_password(new_password)
        except ValueError as exc:
            raise HardBanViolation(str(exc)) from exc
        account.failed_login_count = 0
        account.lockout_until_epoch = None
        self.store.update_account(account)
        revoked = self.sessions.revoke_all_for_account(
            account.account_id, reason="password_reset"
        )
        self.store.append_audit(
            "account.reset_password",
            "ALLOW",
            account_id=account.account_id,
            metadata={"token_id": rec.token_id, "sessions_revoked": revoked},
        )
        return {
            "account_id": account.account_id,
            "password_updated": True,
            "sessions_revoked": revoked,
            "one_time_token_consumed": True,
        }

    def elevate_member_roles(
        self,
        *,
        actor_account_id: str,
        target_account_id: str,
        member_roles: list[str],
    ) -> dict[str, Any]:
        require_self_or_admin(
            actor_account_id=actor_account_id,
            target_account_id=target_account_id,
            store=self.store,
        )
        actor = self.store.get_account(actor_account_id)
        if actor is None:
            raise HardBanViolation("actor account not found")
        if "member_admin" not in set(actor.member_roles):
            raise HardBanViolation(
                "HARD BAN: member privilege escalation blocked — member_admin required"
            )
        target = self.store.get_account(target_account_id)
        if target is None:
            raise HardBanViolation("target account not found")
        normalized = normalize_member_roles(member_roles)
        target.member_roles = normalized
        self.store.update_account(target)
        self.store.append_audit(
            "roles.member.elevate",
            "ALLOW",
            account_id=actor_account_id,
            metadata={"target_account_id": target_account_id, "roles": normalized},
        )
        return {
            "account_id": target_account_id,
            "member_roles": normalized,
            "actor_account_id": actor_account_id,
        }

    def create_org(self, *, owner_account_id: str, name: str) -> dict[str, Any]:
        org = create_organization(
            self.store, name=name, owner_account_id=owner_account_id
        )
        return {
            "org_id": org.org_id,
            "name": org.name,
            "owner_account_id": org.owner_account_id,
            "member_ids": list(org.member_ids),
        }

    def add_org_member(
        self,
        *,
        actor_account_id: str,
        org_id: str,
        member_account_id: str,
        roles: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        return add_org_member(
            self.store,
            actor_account_id=actor_account_id,
            org_id=org_id,
            member_account_id=member_account_id,
            roles=roles,
        )

    def assign_org_roles(
        self,
        account_id: str,
        org_id: str,
        roles: list[str],
        *,
        actor_account_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if actor_account_id is None:
            raise HardBanViolation(
                "HARD BAN: unsigned org role assignment blocked — actor_account_id required"
            )
        return assign_org_roles_authorized(
            self.store,
            actor_account_id=actor_account_id,
            target_account_id=account_id,
            org_id=org_id,
            roles=roles,
        )

    def assign_team_roles(
        self,
        account_id: str,
        team_id: str,
        roles: list[str],
        *,
        actor_account_id: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if actor_account_id is None or not org_id:
            raise HardBanViolation(
                "HARD BAN: unsigned team role assignment blocked — "
                "actor_account_id and org_id required"
            )
        return assign_team_roles_authorized(
            self.store,
            actor_account_id=actor_account_id,
            target_account_id=account_id,
            team_id=team_id,
            org_id=org_id,
            roles=roles,
        )

    def set_tier_manual(self, account_id: str, target_tier: str, *, actor: str) -> dict[str, Any]:
        self.rate_limiter.check("tier_assign", account_id or actor)
        account = self.store.get_account(account_id)
        if account is None:
            raise HardBanViolation("account not found")
        change = assign_tier_manual(
            current_tier=account.tier, target_tier=target_tier, actor=actor
        )
        if change.get("private_execution_access"):
            raise HardBanViolation(
                "HARD BAN: entitlements must never grant private execution access"
            )
        account.tier = target_tier
        self.store.update_account(account)
        self.store.append_audit(
            "entitlement.tier_assign",
            "ALLOW",
            account_id=account_id,
            metadata=change,
        )
        return change

    def check_feature(self, account_id: str, feature: str) -> bool:
        account = self.store.get_account(account_id)
        if account is None:
            raise HardBanViolation("account not found")
        return has_feature(account.tier, feature)

    def require_account_feature(self, account_id: str, feature: str) -> None:
        account = self.store.get_account(account_id)
        if account is None:
            raise HardBanViolation("account not found")
        require_feature(account.tier, feature)

    def entitlements(self, account_id: str) -> dict[str, Any]:
        account = self.store.get_account(account_id)
        if account is None:
            raise HardBanViolation("account not found")
        snap = entitlement_snapshot(account.tier)
        snap["account_id"] = account_id
        if snap.get("private_execution_access"):
            raise HardBanViolation(
                "HARD BAN: entitlements must never grant private execution access"
            )
        return snap

    def create_session_rate_limited(
        self,
        account_id: str,
        *,
        tier: str,
        member_roles: list[str],
        ttl_seconds: int = 3600,
        mfa_challenge_id: Optional[str] = None,
        require_mfa: Optional[bool] = None,
    ) -> dict[str, Any]:
        self.rate_limiter.check("session_create", account_id)
        account = self.store.get_account(account_id)
        if account is None:
            raise HardBanViolation("account not found")
        policy_mfa = False
        if require_mfa is None:
            try:
                policy_mfa = has_feature(account.tier, "mfa_required_org_policy")
            except HardBanViolation:
                policy_mfa = False
            enabled = [
                f
                for f in self.store.list_mfa_factors(account_id)
                if getattr(f, "status", None) == "enabled"
            ]
            require_mfa = bool(policy_mfa and enabled) or bool(enabled)
        return self.sessions.create_session(
            account_id,
            tier=tier,
            member_roles=member_roles,
            ttl_seconds=ttl_seconds,
            mfa_challenge_id=mfa_challenge_id,
            require_mfa=bool(require_mfa),
        )

    def authenticate_rate_limited(self, token: str) -> dict[str, Any]:
        subject = (token or "")[:16] or "anonymous"
        self.rate_limiter.check("session_authenticate", subject)
        return self.sessions.authenticate(token)


_DEFAULT_SERVICE: Optional[PublicAuthMembershipService] = None
_SERVICE_LOCK = __import__("threading").Lock()


def get_default_public_auth_service() -> PublicAuthMembershipService:
    global _DEFAULT_SERVICE
    with _SERVICE_LOCK:
        if _DEFAULT_SERVICE is None:
            _DEFAULT_SERVICE = PublicAuthMembershipService()
        return _DEFAULT_SERVICE
