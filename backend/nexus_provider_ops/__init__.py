"""NEXUS Founder-private Provider Completion Ops V12-C.

Observes incomplete Provider resume SoT (Groq 53/27, SambaNova critic 16/10),
surfaces queue health / Retry-After / capacity windows, enforces checkpoint
safety + completed-case dedupe, and supports manual pause/resume of *ops
scheduling* only.

Hard bans:
- no real Provider resume ownership theft (local Coordinator alone owns real resume)
- no secret logging
- no Demo/exchange
- no PR27 merge
- do not claim V2.3 complete
"""
from __future__ import annotations

from backend.nexus_provider_ops.constants import (
    BASE_COMMIT,
    BRANCH,
    HARD_BANS,
    LANE,
    LANE_NAME,
    PACKAGE,
    REAL_RESUME_OWNER,
    SCHEMA,
    SCHEMA_STATUS,
)
from backend.nexus_provider_ops.plane import ProviderCompletionOpsV12, build_ops_plane
from backend.nexus_provider_ops.resume_boundary import ResumeBoundary, ResumeOwnershipError
from backend.nexus_provider_ops.sot import incomplete_sot_snapshot

__all__ = [
    "BASE_COMMIT",
    "BRANCH",
    "HARD_BANS",
    "LANE",
    "LANE_NAME",
    "PACKAGE",
    "ProviderCompletionOpsV12",
    "REAL_RESUME_OWNER",
    "ResumeBoundary",
    "ResumeOwnershipError",
    "SCHEMA",
    "SCHEMA_STATUS",
    "build_ops_plane",
    "incomplete_sot_snapshot",
]
