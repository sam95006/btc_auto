"""PUB-A Intelligence Publishing Gateway — read-only allow-list boundary.

Sanitizes Private Intelligence into public Decision Intelligence DTOs.
LOCAL/STAGING only. No private-core trading imports. No exchange write.
"""
from __future__ import annotations

from backend.nexus_publishing_gateway.ast_guard import (
    assert_no_private_imports,
    run_ast_mutation_kills,
    scan_forbidden_imports,
)
from backend.nexus_publishing_gateway.constants import (
    ALLOWED_PUBLIC_FIELDS,
    DENIED_PRIVATE_FIELDS,
    HARD_BANS,
    LANE,
    PASS_RECOMMENDATION,
    SCHEMA,
)
from backend.nexus_publishing_gateway.gateway import (
    hard_ban_inventory,
    publish_intelligence,
    publish_public_dto,
)
from backend.nexus_publishing_gateway.side_channel import run_side_channel_suite

__all__ = [
    "ALLOWED_PUBLIC_FIELDS",
    "DENIED_PRIVATE_FIELDS",
    "HARD_BANS",
    "LANE",
    "PASS_RECOMMENDATION",
    "SCHEMA",
    "assert_no_private_imports",
    "hard_ban_inventory",
    "publish_intelligence",
    "publish_public_dto",
    "run_ast_mutation_kills",
    "run_side_channel_suite",
    "scan_forbidden_imports",
]
