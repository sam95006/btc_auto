"""Organization / team access control for the public identity realm.

Prevents cross-org role assignment and unprivileged privilege escalation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from backend.nexus_public_auth.hard_bans import HardBanViolation
from backend.nexus_public_auth.roles import normalize_org_roles, normalize_team_roles
from backend.nexus_public_auth.store import PublicAuthStore, _new_id, _utcnow


ORG_PRIVILEGED_ROLES = frozenset({"org_owner", "org_admin"})
SELF_REGISTER_ROLES = frozenset({"member"})
SELF_REGISTER_TIER = "Free"

# Features that must never appear in any public entitlement matrix.
PRIVATE_EXECUTION_FEATURE_DENYLIST = frozenset(
    {
        "private_execution",
        "exchange_write",
        "place_order",
        "create_order",
        "mainnet_trade",
        "demo_trade",
        "shadow_trade",
        "lesson_memory_admin",
        "founder_operator",
        "checkpoint_admin",
        "private_core_access",
    }
)


@dataclass
class PublicOrganization:
    org_id: str
    name: str
    owner_account_id: str
    member_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)


@dataclass
class PublicTeam:
    team_id: str
    org_id: str
    name: str
    member_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)


def assert_no_private_execution_features(features: set[str] | frozenset[str]) -> None:
    overlap = set(features) & PRIVATE_EXECUTION_FEATURE_DENYLIST
    if overlap:
        raise HardBanViolation(
            f"HARD BAN: public entitlements must never grant private execution: {sorted(overlap)}"
        )


def require_self_or_admin(
    *,
    actor_account_id: str,
    target_account_id: str,
    store: PublicAuthStore,
) -> None:
    if actor_account_id == target_account_id:
        return
    actor = store.get_account(actor_account_id)
    if actor is None:
        raise HardBanViolation("actor account not found")
    if "member_admin" not in set(actor.member_roles):
        raise HardBanViolation(
            "HARD BAN: cross-account access denied — actor lacks member_admin"
        )


def create_organization(
    store: PublicAuthStore,
    *,
    name: str,
    owner_account_id: str,
) -> PublicOrganization:
    owner = store.get_account(owner_account_id)
    if owner is None:
        raise HardBanViolation("owner account not found")
    org = PublicOrganization(
        org_id=_new_id("org"),
        name=name.strip() or "unnamed",
        owner_account_id=owner_account_id,
        member_ids=[owner_account_id],
    )
    with store._lock:
        if not hasattr(store, "organizations"):
            store.organizations = {}
        store.organizations[org.org_id] = org
    # Seed owner ACL on the account.
    owner.org_roles[org.org_id] = ["org_owner"]
    store.update_account(owner)
    store.append_audit(
        "org.create",
        "ALLOW",
        account_id=owner_account_id,
        metadata={"org_id": org.org_id, "name": org.name},
    )
    return org


def get_organization(store: PublicAuthStore, org_id: str) -> Optional[PublicOrganization]:
    orgs = getattr(store, "organizations", {})
    return orgs.get(org_id)


def require_org_membership(store: PublicAuthStore, *, account_id: str, org_id: str) -> None:
    org = get_organization(store, org_id)
    if org is None:
        raise HardBanViolation("organization not found")
    if account_id not in org.member_ids:
        raise HardBanViolation(
            f"HARD BAN: cross-org access denied — account {account_id} not in org {org_id}"
        )


def require_org_privilege(
    store: PublicAuthStore,
    *,
    actor_account_id: str,
    org_id: str,
) -> list[str]:
    require_org_membership(store, account_id=actor_account_id, org_id=org_id)
    actor = store.get_account(actor_account_id)
    if actor is None:
        raise HardBanViolation("actor account not found")
    roles = list(actor.org_roles.get(org_id) or [])
    if not (set(roles) & ORG_PRIVILEGED_ROLES):
        raise HardBanViolation(
            "HARD BAN: member privilege escalation blocked — org_admin/org_owner required"
        )
    return roles


def add_org_member(
    store: PublicAuthStore,
    *,
    actor_account_id: str,
    org_id: str,
    member_account_id: str,
    roles: list[str] | None = None,
) -> dict[str, Any]:
    require_org_privilege(store, actor_account_id=actor_account_id, org_id=org_id)
    member = store.get_account(member_account_id)
    if member is None:
        raise HardBanViolation("member account not found")
    org = get_organization(store, org_id)
    assert org is not None
    if member_account_id not in org.member_ids:
        org.member_ids.append(member_account_id)
    normalized = normalize_org_roles(roles or ["org_member"])
    # Only org_owner may grant org_owner.
    actor_roles = set(store.get_account(actor_account_id).org_roles.get(org_id) or [])
    if "org_owner" in normalized and "org_owner" not in actor_roles:
        raise HardBanViolation(
            "HARD BAN: member privilege escalation blocked — only org_owner may grant org_owner"
        )
    member.org_roles[org_id] = normalized
    store.update_account(member)
    store.append_audit(
        "org.member.add",
        "ALLOW",
        account_id=actor_account_id,
        metadata={
            "org_id": org_id,
            "member_account_id": member_account_id,
            "roles": normalized,
        },
    )
    return {
        "org_id": org_id,
        "member_account_id": member_account_id,
        "roles": normalized,
    }


def assign_org_roles_authorized(
    store: PublicAuthStore,
    *,
    actor_account_id: str,
    target_account_id: str,
    org_id: str,
    roles: list[str],
) -> dict[str, Any]:
    """Authorized org role mutation — replaces the open assign_org_roles path."""
    require_org_privilege(store, actor_account_id=actor_account_id, org_id=org_id)
    require_org_membership(store, account_id=target_account_id, org_id=org_id)
    target = store.get_account(target_account_id)
    if target is None:
        raise HardBanViolation("target account not found")
    normalized = normalize_org_roles(roles)
    actor_roles = set(store.get_account(actor_account_id).org_roles.get(org_id) or [])
    if "org_owner" in normalized and "org_owner" not in actor_roles:
        raise HardBanViolation(
            "HARD BAN: member privilege escalation blocked — only org_owner may grant org_owner"
        )
    # Prevent last owner demotion of self leaving org ownerless (explicit block).
    if (
        target_account_id == actor_account_id
        and "org_owner" in actor_roles
        and "org_owner" not in normalized
    ):
        owners = []
        for aid in get_organization(store, org_id).member_ids:
            acct = store.get_account(aid)
            if acct and "org_owner" in set(acct.org_roles.get(org_id) or []):
                owners.append(aid)
        if owners == [actor_account_id]:
            raise HardBanViolation(
                "HARD BAN: blocked — cannot demote the sole org_owner"
            )
    target.org_roles[org_id] = normalized
    store.update_account(target)
    store.append_audit(
        "roles.org.assign",
        "ALLOW",
        account_id=actor_account_id,
        metadata={
            "org_id": org_id,
            "target_account_id": target_account_id,
            "roles": normalized,
        },
    )
    return {
        "account_id": target_account_id,
        "org_id": org_id,
        "roles": normalized,
        "actor_account_id": actor_account_id,
    }


def assign_team_roles_authorized(
    store: PublicAuthStore,
    *,
    actor_account_id: str,
    target_account_id: str,
    team_id: str,
    org_id: str,
    roles: list[str],
) -> dict[str, Any]:
    require_org_privilege(store, actor_account_id=actor_account_id, org_id=org_id)
    require_org_membership(store, account_id=target_account_id, org_id=org_id)
    target = store.get_account(target_account_id)
    if target is None:
        raise HardBanViolation("target account not found")
    normalized = normalize_team_roles(roles)
    target.team_roles[team_id] = normalized
    store.update_account(target)
    store.append_audit(
        "roles.team.assign",
        "ALLOW",
        account_id=actor_account_id,
        metadata={
            "team_id": team_id,
            "org_id": org_id,
            "target_account_id": target_account_id,
            "roles": normalized,
        },
    )
    return {
        "account_id": target_account_id,
        "team_id": team_id,
        "org_id": org_id,
        "roles": normalized,
        "actor_account_id": actor_account_id,
    }
