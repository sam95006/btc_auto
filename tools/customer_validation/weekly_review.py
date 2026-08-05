"""Weekly Founder review records for Concierge validation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tools.customer_validation.hard_bans import HardBanViolation
from tools.customer_validation.store import append_row, load_collection

GATE_OPTIONS = frozenset({"CONTINUE", "ITERATE", "PIVOT", "KILL", "DEFER"})


def list_weekly_reviews(workspace=None) -> list[dict[str, Any]]:
    return load_collection("weekly_reviews", workspace)


def record_weekly_review(
    *,
    week: int,
    active_participants: int,
    closed_decision_loops: int,
    thesis_completions: int,
    outcome_reviews: int,
    qualitative_notes: str,
    gate_posture: str,
    operator_actions: list[str],
    workspace=None,
) -> dict[str, Any]:
    if gate_posture not in GATE_OPTIONS:
        raise HardBanViolation(f"gate_posture must be one of {sorted(GATE_OPTIONS)}")
    if active_participants < 0 or closed_decision_loops < 0:
        raise HardBanViolation("negative cohort metrics refused")
    # Integrity: cannot claim active participants beyond registry without real enrollments
    from tools.customer_validation.registry import real_participant_count

    registered = real_participant_count(workspace)
    if active_participants > registered:
        raise HardBanViolation(
            "active_participants cannot exceed real_participant_count "
            f"(got {active_participants} > {registered})"
        )
    row = {
        "week": week,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cohort_health": {
            "active_participants": active_participants,
            "closed_decision_loops": closed_decision_loops,
            "thesis_completions": thesis_completions,
            "outcome_reviews": outcome_reviews,
        },
        "qualitative_notes": qualitative_notes,
        "gate_posture": gate_posture,
        "operator_actions": list(operator_actions),
        "fabricated_result_count": 0,
        "pre_registered_gates_only": True,
    }
    return append_row("weekly_reviews", row, workspace)
