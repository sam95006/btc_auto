"""Problem ranking capture for Concierge ICP pain prioritization."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tools.customer_validation.hard_bans import refuse_fabrication
from tools.customer_validation.registry import list_participants
from tools.customer_validation.store import append_row, load_collection

DEFAULT_PROBLEM_CATALOG = (
    "research_burden",
    "decision_rewrite_after_fact",
    "weak_invalidation",
    "alert_noise",
    "tool_sprawl",
    "ai_overconfidence",
    "no_outcome_review",
    "mobile_desktop_split",
)


def list_rankings(workspace=None) -> list[dict[str, Any]]:
    return load_collection("problem_rankings", workspace)


def record_problem_ranking(
    *,
    participant_id: str,
    ranked_problems: list[str],
    workspace=None,
) -> dict[str, Any]:
    known = {p["participant_id"] for p in list_participants(workspace)}
    if participant_id not in known:
        refuse_fabrication("problem ranking refused for unknown participant_id")
    if not ranked_problems:
        refuse_fabrication("empty problem ranking refused")
    unknown = [p for p in ranked_problems if p not in DEFAULT_PROBLEM_CATALOG]
    if unknown:
        refuse_fabrication(f"unknown problem ids: {unknown}")
    row = {
        "participant_id": participant_id,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ranked_problems": list(ranked_problems),
        "catalog_version": "NEXUS_PROBLEM_CATALOG_V1",
        "fabricated": False,
    }
    return append_row("problem_rankings", row, workspace)
