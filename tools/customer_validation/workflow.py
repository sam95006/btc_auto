"""Current-workflow mapping for Week-0 Concierge intake."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tools.customer_validation.hard_bans import refuse_fabrication
from tools.customer_validation.registry import list_participants
from tools.customer_validation.store import append_row, load_collection

WORKFLOW_FIELDS = (
    "tools_used",
    "decision_artifacts_today",
    "research_minutes_typical_week",
    "invalidation_practice",
    "outcome_review_practice",
    "desired_nexus_fit",
)


def list_workflow_maps(workspace=None) -> list[dict[str, Any]]:
    return load_collection("workflow_maps", workspace)


def record_workflow_map(
    *,
    participant_id: str,
    fields: dict[str, Any],
    workspace=None,
) -> dict[str, Any]:
    known = {p["participant_id"] for p in list_participants(workspace)}
    if participant_id not in known:
        refuse_fabrication("workflow map refused for unknown participant_id")
    missing = [k for k in WORKFLOW_FIELDS if k not in fields or fields[k] in (None, "")]
    if missing:
        refuse_fabrication(f"workflow map incomplete: {missing}")
    row = {
        "participant_id": participant_id,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fields": {k: fields[k] for k in WORKFLOW_FIELDS},
        "spine": ["TODAY", "THESIS", "DECISION", "MONITOR", "REVIEW"],
        "standalone_generic_chat_forbidden": True,
        "fabricated": False,
    }
    return append_row("workflow_maps", row, workspace)
