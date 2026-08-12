"""BLOCKED / BLOCKED_AMBIGUOUS semantics across lifecycle scopes."""
from __future__ import annotations

from typing import Any

# Scopes that may enter BLOCKED_AMBIGUOUS (requires adjudication; not silent resume).
BLOCKED_AMBIGUOUS_SCOPES: frozenset[str] = frozenset(
    {"decision", "intent", "position", "reflection"}
)

# Session uses terminal BLOCKED (not BLOCKED_AMBIGUOUS).
# ControlPlane uses FAILED_SAFE / KILLED (no BLOCKED_AMBIGUOUS token).


def blocked_ambiguous_policy() -> dict[str, Any]:
    return {
        "schema": "nexus_lifecycle_blocked_ambiguous_v11_1",
        "tokens": {
            "BLOCKED": {
                "scopes": ["session"],
                "terminal": True,
                "resume_allowed": False,
                "meaning": (
                    "Session fail-closed terminal. No further trading-loop progress. "
                    "Maps via adapter to ControlPlane FAILED_SAFE or KILLED only."
                ),
            },
            "BLOCKED_AMBIGUOUS": {
                "scopes": sorted(BLOCKED_AMBIGUOUS_SCOPES),
                "terminal": False,
                "resume_allowed": False,
                "adjudication_required": True,
                "meaning": (
                    "Ambiguous evidence / race / partial observability. "
                    "Must not auto-advance to success terminals. "
                    "Allowed exits: CLOSED/CANCELLED/SUPERSEDED/INCOMPLETE/FAILED_SAFE "
                    "per owning scope transitions only."
                ),
            },
            "FAILED_SAFE": {
                "scopes": ["session", "control_plane", "reflection"],
                "terminal": True,
                "resume_allowed": False,
                "meaning": "Hard fail-closed terminal shared as token but scoped via adapter.",
            },
        },
        "forbidden": [
            {
                "action": "silent_resume_from_BLOCKED_AMBIGUOUS",
                "allowed": False,
            },
            {
                "action": "equate_session_BLOCKED_with_decision_BLOCKED_AMBIGUOUS",
                "allowed": False,
                "reason": "Different scopes and semantics; no adapter identity.",
            },
            {
                "action": "control_plane_BLOCKED_AMBIGUOUS_token",
                "allowed": False,
                "reason": "ControlPlane vocabulary has no BLOCKED_AMBIGUOUS.",
            },
        ],
        "order_note": (
            "Order scope uses REJECTED/CANCELLED/EXPIRED rather than BLOCKED_AMBIGUOUS "
            "in execution_contract_v1_1; Order is intentionally excluded from "
            "BLOCKED_AMBIGUOUS_SCOPES."
        ),
    }
