"""Hard-ban enforcement for V14-H Candidate Triage Control."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_candidate_triage.constants import (
    ALLOWED_TRIAGE_STATUSES,
    BLOCK_REASON,
    FORBIDDEN_OUTPUT_STATUSES,
    HARD_BANS,
    PLAN_STATUS_PLANNED_NOT_EXECUTED,
)


def default_control_flags() -> dict[str, Any]:
    return {
        "Founder_authorization_present": False,
        "founder_authorization_present": False,
        "formal_walk_forward_executed": False,
        "oos_reservation_created": False,
        "oos_executed": False,
        "oos_consumed": False,
        "oos_touched": False,
        "strategy_selected": False,
        "strategy_promoted": False,
        "demo_eligibility": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "pr27_merged": False,
        "mainnet": False,
        "real_money": False,
        "auto_integrated": False,
        "qualification_ready_count": 0,
        "qualified_output_count": 0,
        "promoted_output_count": 0,
        "demo_ready_output_count": 0,
    }


def assert_status_allowed(status: str) -> None:
    if status in FORBIDDEN_OUTPUT_STATUSES:
        raise RuntimeError(f"FORBIDDEN_OUTPUT_STATUS:{status}")
    if status not in ALLOWED_TRIAGE_STATUSES:
        raise RuntimeError(f"UNKNOWN_TRIAGE_STATUS:{status}")


def refuse_formal_walk_forward(candidate_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "FORMAL_WALK_FORWARD",
        "candidate_id": candidate_id,
        "reason": BLOCK_REASON,
        "status": PLAN_STATUS_PLANNED_NOT_EXECUTED,
        "formal_walk_forward_executed": False,
    }


def refuse_oos(
    *,
    kind: str = "OOS_RESERVATION",
    candidate_id: str | None = None,
) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": kind,
        "candidate_id": candidate_id,
        "reason": BLOCK_REASON,
        "oos_reservation_created": False,
        "oos_executed": False,
        "oos_consumed": False,
        "oos_touched": False,
    }


def refuse_select(candidate_id: str) -> dict[str, Any]:
    return {
        "allowed": False,
        "selected": False,
        "candidate_id": candidate_id,
        "reason": "STRATEGY_SELECTION_BANNED_V14_H",
    }


def refuse_promote(candidate_id: str) -> dict[str, Any]:
    return {
        "allowed": False,
        "promoted": False,
        "candidate_id": candidate_id,
        "reason": "STRATEGY_PROMOTION_BANNED_V14_H",
    }


def refuse_demo(candidate_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "DEMO_ORDER",
        "candidate_id": candidate_id,
        "reason": "DEMO_ORDERS_BANNED_V14_H",
        "demo_order_count": 0,
        "demo_eligibility": False,
    }


def refuse_qualify(candidate_id: str) -> dict[str, Any]:
    return {
        "allowed": False,
        "qualified": False,
        "candidate_id": candidate_id,
        "reason": "QUALIFIED_OUTPUT_BANNED_V14_H",
        "forbidden_status": "QUALIFIED",
    }


def refuse_demo_ready(candidate_id: str) -> dict[str, Any]:
    return {
        "allowed": False,
        "demo_ready": False,
        "candidate_id": candidate_id,
        "reason": "DEMO_READY_OUTPUT_BANNED_V14_H",
        "forbidden_status": "DEMO_READY",
    }


def refuse_auto_integrate() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "AUTO_INTEGRATE",
        "reason": "AUTO_INTEGRATE_BANNED_V14_H",
        "auto_integrated": False,
    }


def refuse_exchange_write() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "EXCHANGE_WRITE",
        "reason": "EXCHANGE_WRITES_BANNED_V14_H",
        "exchange_write_attempt_count": 0,
    }


def hard_ban_probe_matrix(candidate_id: str = "SYN_V14H_PROBE") -> dict[str, Any]:
    """Adversarial probe: every hard-ban surface must refuse."""
    probes = {
        "force_walk_forward": refuse_formal_walk_forward(candidate_id),
        "force_oos_reservation": refuse_oos(kind="OOS_RESERVATION", candidate_id=candidate_id),
        "force_oos_consume": refuse_oos(kind="OOS_CONSUMPTION", candidate_id=candidate_id),
        "force_select": refuse_select(candidate_id),
        "force_promote": refuse_promote(candidate_id),
        "force_demo": refuse_demo(candidate_id),
        "force_qualify": refuse_qualify(candidate_id),
        "force_demo_ready": refuse_demo_ready(candidate_id),
        "force_auto_integrate": refuse_auto_integrate(),
        "force_exchange_write": refuse_exchange_write(),
    }
    all_refused = all(not p.get("allowed") and not p.get("executed", False) for p in probes.values())
    return {
        "probes": probes,
        "all_refused": all_refused,
        "hard_bans": list(HARD_BANS),
        "flags": default_control_flags(),
    }


def sanitize_triage_record(record: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed rewrite of any forbidden status leakage."""
    out = deepcopy(record)
    status = out.get("triage_status")
    if status in FORBIDDEN_OUTPUT_STATUSES:
        raise RuntimeError(f"FORBIDDEN_OUTPUT_STATUS:{status}")
    if status is not None:
        assert_status_allowed(str(status))
    out["qualified"] = False
    out["selected"] = False
    out["promoted"] = False
    out["demo_ready"] = False
    out["qualification_ready"] = False
    out["formal_walk_forward_executed"] = False
    out["oos_touched"] = False
    return out
