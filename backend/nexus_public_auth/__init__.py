"""NEXUS Public Auth & Membership Foundation (PUB-H).

Non-production foundations for a separate public identity realm.
No live billing. No shared private JWT issuer. No private admin session reuse.
"""
from __future__ import annotations

from backend.nexus_public_auth.constants import (
    HARD_BANS,
    MEMBERSHIP_TIERS,
    PACKAGE,
    PUBLIC_IDENTITY_REALM,
    PUBLIC_JWT_ISSUER,
    SCHEMA,
)
from backend.nexus_public_auth.hard_bans import HardBanViolation
from backend.nexus_public_auth.service import PublicAuthMembershipService

__all__ = [
    "HARD_BANS",
    "MEMBERSHIP_TIERS",
    "PACKAGE",
    "PUBLIC_IDENTITY_REALM",
    "PUBLIC_JWT_ISSUER",
    "SCHEMA",
    "HardBanViolation",
    "PublicAuthMembershipService",
]
