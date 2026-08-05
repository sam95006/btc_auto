"""Facade service composing the PUB-H public auth & membership foundation."""
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
from backend.nexus_public_auth.roles import (
    normalize_member_roles,
    normalize_org_roles,
    normalize_team_roles,
)
from backend.nexus_public_auth.sessions import SessionService
from backend.nexus_public_auth.store import PublicAuthStore, get_default_store


class PublicAuthMembershipService:
    """Non-production public identity + membership foundation."""

    def __init__(self, store: Optional[PublicAuthStore] = None, issuer: Optional[PublicJwtIssuer] = None):
        assert_env_hard_bans()
        self.store = store or get_default_store()
        self.issuer = issuer or PublicJwtIssuer()
        self.sessions = SessionService(self.store, self.issuer)
        self.consent = ConsentService(self.store)
        self.lifecycle = AccountLifecycleService(self.store, self.sessions)

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
    ) -> dict[str, Any]:
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

    def assign_org_roles(self, account_id: str, org_id: str, roles: list[str]) -> dict[str, Any]:
        account = self.store.get_account(account_id)
        if account is None:
            raise HardBanViolation("account not found")
        normalized = normalize_org_roles(roles)
        account.org_roles[org_id] = normalized
        self.store.update_account(account)
        self.store.append_audit(
            "roles.org.assign",
            "ALLOW",
            account_id=account_id,
            metadata={"org_id": org_id, "roles": normalized},
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
        account = self.store.get_account(account_id)
        if account is None:
            raise HardBanViolation("account not found")
        change = assign_tier_manual(
            current_tier=account.tier, target_tier=target_tier, actor=actor
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
        return snap
