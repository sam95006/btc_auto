"""NEXUS Founder-private Reflection V2.3 Completion Ops V13-B.

Hardens private operations needed to complete real V2.3 calibration around
incomplete Provider SoT (checkpoint counters: Groq 53/27, SambaNova critic 16/10).

Hard bans:
- no real Provider resume ownership (local Coordinator alone)
- no secret logging
- no policy-effect Lessons while incomplete
- no quality eval before complete denominators
- no Demo/exchange
- no PR27 merge
- do not claim V2.3 complete
- Background Agent: sanitized fixtures only
"""
from __future__ import annotations

from backend.nexus_v23_completion_ops.constants import (
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
from backend.nexus_v23_completion_ops.plane import V23CompletionOpsV13, build_ops_plane
from backend.nexus_v23_completion_ops.resume_boundary import ResumeBoundary, ResumeOwnershipError
from backend.nexus_v23_completion_ops.sot import incomplete_sot_snapshot

__all__ = [
    "BASE_COMMIT",
    "BRANCH",
    "HARD_BANS",
    "LANE",
    "LANE_NAME",
    "PACKAGE",
    "REAL_RESUME_OWNER",
    "ResumeBoundary",
    "ResumeOwnershipError",
    "SCHEMA",
    "SCHEMA_STATUS",
    "V23CompletionOpsV13",
    "build_ops_plane",
    "incomplete_sot_snapshot",
]
