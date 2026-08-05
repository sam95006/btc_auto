"""PUB2-G Concierge workflow spine — ordered local/staging steps."""
from __future__ import annotations

from typing import Any

from tools.customer_validation.consent import list_consents
from tools.customer_validation.decision_object_concierge import list_deliveries
from tools.customer_validation.evidence import (
    list_conversions,
    list_objections,
    list_retention,
    list_wtp,
    paid_pilot_count,
)
from tools.customer_validation.interview import completed_interview_count, list_interviews
from tools.customer_validation.problem_ranking import list_rankings
from tools.customer_validation.registry import list_participants, real_participant_count
from tools.customer_validation.store import COLLECTIONS, ensure_workspace, load_collection
from tools.customer_validation.watchlist_onboarding import (
    list_watchlist_onboardings,
    watchlist_onboarding_count,
)
from tools.customer_validation.weekly_review import list_weekly_reviews

WORKFLOW_STEPS: tuple[str, ...] = (
    "consent",
    "interview",
    "problem_ranking",
    "watchlist_onboarding",
    "decision_object_delivery",
    "weekly_review",
    "retention",
    "willingness_to_pay",
    "objections",
    "pilot_conversion",
)


def compute_workflow_counters(workspace=None) -> dict[str, int]:
    """All counters stay 0 until real participants create genuine records."""
    ensure_workspace(workspace)
    return {
        "real_participant_count": real_participant_count(workspace),
        "consent_count": len(list_consents(workspace)),
        "interview_started_count": sum(
            1 for row in list_interviews(workspace) if row.get("status") == "in_progress"
        ),
        "completed_interview_count": completed_interview_count(workspace),
        "problem_ranking_count": len(list_rankings(workspace)),
        "watchlist_onboarding_count": watchlist_onboarding_count(workspace),
        "decision_object_delivery_count": len(list_deliveries(workspace)),
        "weekly_review_count": len(list_weekly_reviews(workspace)),
        "retention_evidence_count": len(list_retention(workspace)),
        "wtp_evidence_count": len(list_wtp(workspace)),
        "objection_count": len(list_objections(workspace)),
        "pilot_conversion_intent_count": sum(
            1
            for row in list_conversions(workspace)
            if row.get("conversion_type") == "paid_pilot"
            and row.get("status") in ("intent_only", "confirmed")
        ),
        "paid_pilot_count": paid_pilot_count(workspace),
        "fabricated_result_count": _fabricated_flag_count(workspace),
    }


def _fabricated_flag_count(workspace=None) -> int:
    total = 0
    for name in COLLECTIONS:
        for row in load_collection(name, workspace):
            if row.get("fabricated") is True:
                total += 1
    return total


REQUIRED_ZERO_UNTIL_REAL: tuple[str, ...] = (
    "real_participant_count",
    "consent_count",
    "interview_started_count",
    "completed_interview_count",
    "problem_ranking_count",
    "watchlist_onboarding_count",
    "decision_object_delivery_count",
    "weekly_review_count",
    "retention_evidence_count",
    "wtp_evidence_count",
    "objection_count",
    "pilot_conversion_intent_count",
    "paid_pilot_count",
    "fabricated_result_count",
)


def workflow_spine_status(workspace=None) -> dict[str, Any]:
    counters = compute_workflow_counters(workspace)
    steps = []
    for step in WORKFLOW_STEPS:
        key = {
            "consent": "consent_count",
            "interview": "completed_interview_count",
            "problem_ranking": "problem_ranking_count",
            "watchlist_onboarding": "watchlist_onboarding_count",
            "decision_object_delivery": "decision_object_delivery_count",
            "weekly_review": "weekly_review_count",
            "retention": "retention_evidence_count",
            "willingness_to_pay": "wtp_evidence_count",
            "objections": "objection_count",
            "pilot_conversion": "paid_pilot_count",
        }[step]
        steps.append(
            {
                "step": step,
                "counter_key": key,
                "count": counters[key],
                "ready": True,
                "note": "count remains 0 until real people participate",
            }
        )
    return {
        "schema": "NEXUS_PUB2_G_CONCIERGE_WORKFLOW_SPINE_V1",
        "lane": "PUB2-G",
        "environment": "local_staging",
        "steps": steps,
        "step_ids": list(WORKFLOW_STEPS),
        "counters": counters,
        "required_zero_until_real": list(REQUIRED_ZERO_UNTIL_REAL),
        "all_required_zeros": all(counters[k] == 0 for k in REQUIRED_ZERO_UNTIL_REAL),
        "participants_preview": [
            {"participant_id": p["participant_id"], "enrollment_source": p["enrollment_source"]}
            for p in list_participants(workspace)
        ],
        "status_json_emitted": False,
        "fabricated_results_forbidden": True,
    }
