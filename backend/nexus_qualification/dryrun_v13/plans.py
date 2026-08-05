"""Eligibility *plans* only — Walk-forward / Risk / OOS / Demo.

Plans are generated from Discovery outputs for dry-run control visibility.
Nothing is executed, reserved, consumed, granted, or ordered.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_qualification.dryrun_v13.constants import PLAN_STATUS_PLANNED_NOT_EXECUTED


def build_walk_forward_plan(candidate: dict[str, Any], *, as_of_ms: int) -> dict[str, Any]:
    interval = candidate.get("development_interval") or {}
    start = int(interval.get("start_ms") or (as_of_ms - 60 * 86_400_000))
    end = int(interval.get("end_ms") or (as_of_ms - 30 * 86_400_000))
    mid = start + (end - start) // 2
    folds = [
        {
            "fold_id": "WF_FOLD_TRAIN",
            "role": "train_plan",
            "start_ms": start,
            "end_ms": mid,
        },
        {
            "fold_id": "WF_FOLD_TEST",
            "role": "test_plan",
            "start_ms": mid + 1,
            "end_ms": end,
        },
    ]
    return {
        "candidate_id": candidate.get("candidate_id"),
        "plan_kind": "WALK_FORWARD",
        "status": PLAN_STATUS_PLANNED_NOT_EXECUTED,
        "formal_walk_forward_executed": False,
        "folds": folds,
        "fold_count": len(folds),
        "as_of_ms": as_of_ms,
        "note": "Walk-forward plan only; formal WF remains BLOCKED / not executed.",
    }


def build_risk_review_plan(candidate: dict[str, Any]) -> dict[str, Any]:
    checks = [
        "concentration_limits",
        "cost_stress",
        "drawdown_bound",
        "regime_fragility",
        "multiple_comparison_tax",
    ]
    return {
        "candidate_id": candidate.get("candidate_id"),
        "plan_kind": "RISK_REVIEW",
        "status": PLAN_STATUS_PLANNED_NOT_EXECUTED,
        "risk_review_executed": False,
        "planned_checks": checks,
        "check_count": len(checks),
        "note": "Risk Review plan only; formal Risk Review remains BLOCKED.",
    }


def build_oos_reservation_plan(candidate: dict[str, Any], *, as_of_ms: int) -> dict[str, Any]:
    """Propose an untouched OOS window — do not reserve or consume."""
    # Place proposed OOS after development end, still before as_of.
    interval = candidate.get("development_interval") or {}
    dev_end = int(interval.get("end_ms") or (as_of_ms - 30 * 86_400_000))
    proposed_start = min(dev_end + 86_400_000, as_of_ms - 14 * 86_400_000)
    proposed_end = as_of_ms - 7 * 86_400_000
    return {
        "candidate_id": candidate.get("candidate_id"),
        "plan_kind": "OOS_RESERVATION",
        "status": PLAN_STATUS_PLANNED_NOT_EXECUTED,
        "oos_reservation_created": False,
        "oos_executed": False,
        "oos_consumed": False,
        "real_oos_touched": False,
        "proposed_interval": {
            "start_ms": proposed_start,
            "end_ms": proposed_end,
            "category": "proposed_untouched_oos_plan_only",
        },
        "as_of_ms": as_of_ms,
        "note": "OOS reservation plan only; real OOS is neither reserved nor consumed.",
    }


def build_demo_eligibility_plan(candidate: dict[str, Any]) -> dict[str, Any]:
    criteria = [
        "formal_walk_forward_passed",
        "risk_review_passed",
        "oos_executed_and_passed",
        "founder_authorization_present",
        "no_hard_ban_violations",
    ]
    return {
        "candidate_id": candidate.get("candidate_id"),
        "plan_kind": "DEMO_ELIGIBILITY",
        "status": PLAN_STATUS_PLANNED_NOT_EXECUTED,
        "demo_eligibility_granted": False,
        "demo_order_count": 0,
        "planned_criteria": criteria,
        "criteria_satisfied_count": 0,
        "note": "Demo eligibility plan only; Demo eligibility remains BLOCKED / not granted.",
    }


def build_all_eligibility_plans(
    candidates: list[dict[str, Any]],
    *,
    as_of_ms: int,
) -> dict[str, Any]:
    wf = [build_walk_forward_plan(c, as_of_ms=as_of_ms) for c in candidates]
    risk = [build_risk_review_plan(c) for c in candidates]
    oos = [build_oos_reservation_plan(c, as_of_ms=as_of_ms) for c in candidates]
    demo = [build_demo_eligibility_plan(c) for c in candidates]
    return {
        "walk_forward_plans": deepcopy(wf),
        "risk_review_plans": deepcopy(risk),
        "oos_reservation_plans": deepcopy(oos),
        "demo_eligibility_plans": deepcopy(demo),
        "formal_walk_forward_executed": False,
        "oos_reservation_created": False,
        "oos_executed": False,
        "oos_consumed": False,
        "demo_eligibility_granted": False,
        "demo_order_count": 0,
        "all_plans_not_executed": True,
    }
