"""NEXUS Public Auth Entitlement & Organization Security (PUB2-F).

Non-production foundations for a separate public identity realm.
MFA-ready abstraction. Auth rate limits. Org/team roles.
Free/Pro/Elite/Enterprise entitlements that never grant private execution.
No live billing. No shared private JWT issuer. No private admin session reuse.
"""
from __future__ import annotations

from backend.nexus_public_auth.constants import (
    HARD_BANS,
    MEMBERSHIP_TIERS,
    PACKAGE,
    PRIVATE_EXECUTION_FEATURE_DENYLIST,
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
    "PRIVATE_EXECUTION_FEATURE_DENYLIST",
    "PUBLIC_IDENTITY_REALM",
    "PUBLIC_JWT_ISSUER",
    "SCHEMA",
    "HardBanViolation",
    "PublicAuthMembershipService",
]
