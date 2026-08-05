"""Member / organization / team role helpers for the public identity realm."""
from __future__ import annotations

from typing import Iterable

from backend.nexus_public_auth.constants import MEMBER_ROLES, ORG_ROLES, TEAM_ROLES
from backend.nexus_public_auth.hard_bans import HardBanViolation


PRIVATE_ROLE_DENYLIST = frozenset(
    {
        "founder",
        "founder_admin",
        "private_operator",
        "operator_admin",
        "exchange_writer",
        "mainnet_operator",
        "lesson_memory_admin",
        "checkpoint_admin",
    }
)


def normalize_roles(roles: Iterable[str], allowed: frozenset[str], *, kind: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in roles:
        role = str(raw).strip().lower()
        if not role:
            continue
        if role in PRIVATE_ROLE_DENYLIST or role.startswith("private_"):
            raise HardBanViolation(
                f"HARD BAN: private/founder role {role!r} cannot be assigned in public realm"
            )
        if role not in allowed:
            raise HardBanViolation(f"unknown {kind} role: {role}")
        if role not in seen:
            seen.add(role)
            out.append(role)
    return out


def normalize_member_roles(roles: Iterable[str]) -> list[str]:
    return normalize_roles(roles, MEMBER_ROLES, kind="member")


def normalize_org_roles(roles: Iterable[str]) -> list[str]:
    return normalize_roles(roles, ORG_ROLES, kind="org")


def normalize_team_roles(roles: Iterable[str]) -> list[str]:
    return normalize_roles(roles, TEAM_ROLES, kind="team")


def has_role(assigned: Iterable[str], required: str) -> bool:
    return required in set(assigned)
