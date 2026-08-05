"""Interview workflow — records only after real participant enrollment."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tools.customer_validation.hard_bans import HardBanViolation, refuse_fabrication
from tools.customer_validation.registry import list_participants
from tools.customer_validation.store import append_row, load_collection

INTERVIEW_BLOCKS = (
    "current_decision_workflow",
    "where_decisions_lost",
    "invalidation_habits",
    "tool_spend_and_pain",
    "ai_trust_experiences",
    "process_vs_luck",
    "no_action_decisions",
    "stated_wtp_hypothesis_only",
    "hard_no_buy_thresholds",
    "auto_trading_demand",
)


def list_interviews(workspace=None) -> list[dict[str, Any]]:
    return load_collection("interviews", workspace)


def completed_interview_count(workspace=None) -> int:
    return sum(1 for row in list_interviews(workspace) if row.get("status") == "completed")


def start_interview(*, participant_id: str, workspace=None) -> dict[str, Any]:
    known = {p["participant_id"] for p in list_participants(workspace)}
    if participant_id not in known:
        refuse_fabrication("interview start refused for unknown participant_id")
    row = {
        "participant_id": participant_id,
        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "in_progress",
        "blocks": {b: {"answered": False, "notes": ""} for b in INTERVIEW_BLOCKS},
        "fabricated": False,
    }
    return append_row("interviews", row, workspace)


def complete_interview(
    *,
    participant_id: str,
    block_notes: dict[str, str],
    auto_trading_mandatory: bool,
    workspace=None,
) -> dict[str, Any]:
    known = {p["participant_id"] for p in list_participants(workspace)}
    if participant_id not in known:
        refuse_fabrication("interview complete refused for unknown participant_id")
    if auto_trading_mandatory:
        raise HardBanViolation("participant disqualified: auto-trading required")
    if any(not (block_notes.get(b) or "").strip() for b in INTERVIEW_BLOCKS):
        raise HardBanViolation("all interview blocks require real notes; no empty fabrication")
    row = {
        "participant_id": participant_id,
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "completed",
        "blocks": {
            b: {"answered": True, "notes": block_notes[b].strip()} for b in INTERVIEW_BLOCKS
        },
        "auto_trading_mandatory": False,
        "wtp_prices_validated": False,
        "fabricated": False,
    }
    return append_row("interviews", row, workspace)
