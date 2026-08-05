"""Facade service composing PUB2-F public auth entitlement & org security."""
from __future__ import annotations

from typing import Any, Optional

from backend.nexus_public_auth.account_lifecycle import AccountLifecycleService
from backend.nexus_public_auth.consent import ConsentService
from backend.nexus_public_auth.constants import (
    BRANCH,
    DEPLOYMENT_MODE,
    HARD_BANS,
    LANE,
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
from backend.nexus_public_auth.jwt_issuer import PublicJwtIssuer
from backend.nexus_public_auth.mfa import MfaService
from backend.nexus_public_auth.rate_limit import AuthRateLimiter, get_default_rate_limiter
from backend.nexus_public_auth.roles import (
    normalize_member_roles,
    normalize_org_roles,
    normalize_team_roles,
)
from backend.nexus_public_auth.sessions import SessionService
from backend.nexus_public_auth.store import PublicAuthStore, get_default_store


class PublicAuthMembershipService:
    """Non-production public identity + entitlement + org security foundation."""

    def __init__(
        self,
        store: Optional[PublicAuthStore] = None,
        issuer: Optional[PublicJwtIssuer] = None,
        rate_limiter: Optional[AuthRateLimiter] = None,
    ):
        assert_env_hard_bans()
        self.store = store or get_default_store()
        self.issuer = issuer or PublicJwtIssuer()
        self.rate_limiter = rate_limiter or get_default_rate_limiter()
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
            "issuer_fingerprint": self.issuer.fingerprint(),
        }

    def register_member(
        self,
        email: str,
        display_name: str,
        *,
        tier: str = "Free",
        member_roles: Optional[list[str]] = None,
        rate_subject: Optional[str] = None,
    ) -> dict[str, Any]:
        subject = (rate_subject or email or "anonymous").strip().lower() or "anonymous"
        self.rate_limiter.check("register", subject)
        roles = normalize_member_roles(member_roles or ["member"])
        assert_valid_tier(tier)
        account = self.store.create_account(email, display_name, tier=tier)
        account.member_roles = roles
        self.store.update_account(account)
        self.store.append_audit(
            "account.register",
            "ALLOW",
            account_id=account.account_id,
            metadata={"tier": tier, "member_roles": roles},
        )
        # Terms + privacy must be explicitly consented later; default denied.
        return {
            "account_id": account.account_id,
            "email": account.email,
            "tier": account.tier,
            "member_roles": roles,
            "realm": PUBLIC_IDENTITY_REALM,
        }

    def assign_org_roles(
        self,
        account_id: str,
        org_id: str,
        roles: list[str],
        *,
        actor_account_id: Optional[str] = None,
    ) -> dict[str, Any]:
        from backend.nexus_public_auth.roles import (
            ORG_PRIVILEGED_ROLES,
            assert_org_role_assignment_allowed,
        )

        account = self.store.get_account(account_id)
        if account is None:
            raise HardBanViolation("account not found")
        normalized = normalize_org_roles(roles)
        privileged_targets = set(normalized) & ORG_PRIVILEGED_ROLES
        if privileged_targets:
            existing_privileged = False
            with self.store._lock:
                for acct in self.store.accounts.values():
                    if set(acct.org_roles.get(org_id, [])) & ORG_PRIVILEGED_ROLES:
                        existing_privileged = True
                        break
            if actor_account_id is None:
                if existing_privileged:
                    raise HardBanViolation(
                        "HARD BAN: privileged org role assignment requires actor_account_id"
                    )
                # Non-production bootstrap of first org_owner/admin only.
            else:
                actor = self.store.get_account(actor_account_id)
                if actor is None:
                    raise HardBanViolation("actor account not found")
                actor_roles = list(actor.org_roles.get(org_id, []))
                assert_org_role_assignment_allowed(
                    actor_roles=actor_roles, target_roles=normalized
                )
        account.org_roles[org_id] = normalized
        self.store.update_account(account)
        self.store.append_audit(
            "roles.org.assign",
            "ALLOW",
            account_id=account_id,
            metadata={
                "org_id": org_id,
                "roles": normalized,
                "actor_account_id": actor_account_id,
                "bootstrap": bool(privileged_targets and actor_account_id is None),
            },
        )
        return {"account_id": account_id, "org_id": org_id, "roles": normalized}

    def assign_team_roles(self, account_id: str, team_id: str, roles: list[str]) -> dict[str, Any]:
        account = self.store.get_account(account_id)
        if account is None:
            raise HardBanViolation("account not found")
        normalized = normalize_team_roles(roles)
        account.team_roles[team_id] = normalized
        self.store.update_account(account)
        self.store.append_audit(
            "roles.team.assign",
            "ALLOW",
            account_id=account_id,
            metadata={"team_id": team_id, "roles": normalized},
        )
        return {"account_id": account_id, "team_id": team_id, "roles": normalized}

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
            # Enterprise org policy: MFA required once factors are enrolled.
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
        # Subject is token prefix only for bucketing — never log full token.
        subject = (token or "")[:16] or "anonymous"
        self.rate_limiter.check("session_authenticate", subject)
        return self.sessions.authenticate(token)
