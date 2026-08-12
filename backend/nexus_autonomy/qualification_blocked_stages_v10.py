"""V10 qualification blocked-stage matrix.

Control infrastructure only. Every stage defaults to BLOCKED and refuses
execution. Does not run Candidate Freeze, Replay, Walk-forward, Risk Review,
OOS reservation, or Demo eligibility.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

# Founder Lane F owned stages (blocked-only control plane).
BLOCKED_QUALIFICATION_STAGES_V10: tuple[str, ...] = (
    "CANDIDATE_FREEZE",
    "REPLAY",
    "WALK_FORWARD",
    "RISK_REVIEW",
    "OOS_RESERVATION",
    "DEMO_ELIGIBILITY",
)

STAGE_STATUS_BLOCKED = "BLOCKED"
STAGE_STATUS_EXECUTED = "EXECUTED"  # unreachable in V10 control plane

BLOCK_REASON = "STAGE_DEFAULT_BLOCKED_V10_CONTROL_PLANE_ONLY"

# Human-facing labels aligned to Founder directive wording.
STAGE_LABELS: dict[str, str] = {
    "CANDIDATE_FREEZE": "Candidate Freeze",
    "REPLAY": "Replay",
    "WALK_FORWARD": "Walk-forward",
    "RISK_REVIEW": "Risk Review",
    "OOS_RESERVATION": "OOS reservation",
    "DEMO_ELIGIBILITY": "Demo eligibility",
}

HARD_BANS: tuple[str, ...] = (
    "no_candidate_freeze_execution",
    "no_replay_execution",
    "no_walk_forward_execution",
    "no_risk_review_execution",
    "no_oos_reservation",
    "no_oos_execution",
    "no_september_reserved_oos_consumption",
    "no_demo_eligibility_grant",
    "no_demo_shadow_exchange_writes",
    "no_strategy_selection",
    "no_strategy_promotion",
    "no_merge_deploy",
)


def default_blocked_stage_matrix() -> dict[str, str]:
    """Every owned stage starts and remains BLOCKED."""
    return {stage: STAGE_STATUS_BLOCKED for stage in BLOCKED_QUALIFICATION_STAGES_V10}


def blocked_stage_matrix_document() -> dict[str, Any]:
    """Immutable-ready blocked stage matrix document."""
    stages = default_blocked_stage_matrix()
    return {
        "schema": "NEXUS_QUALIFICATION_BLOCKED_STAGES_V10",
        "stage_order": list(BLOCKED_QUALIFICATION_STAGES_V10),
        "stage_labels": dict(STAGE_LABELS),
        "stages": stages,
        "all_stages_blocked": all(v == STAGE_STATUS_BLOCKED for v in stages.values()),
        "block_reason": BLOCK_REASON,
        "hard_bans": list(HARD_BANS),
        "note": (
            "All stages default BLOCKED. V10 control plane does not execute "
            "Candidate Freeze, Replay, Walk-forward, Risk Review, OOS reservation, "
            "or Demo eligibility."
        ),
    }


class BlockedStageControllerV10:
    """Refuse all stage advances. Fail-closed control surface."""

    def __init__(self) -> None:
        self.stages: dict[str, str] = default_blocked_stage_matrix()
        self.attempt_log: list[dict[str, Any]] = []

    def attempt_execute_stage(self, stage: str) -> dict[str, Any]:
        """Refuse execution for known and unknown stages alike when not authorized."""
        if stage not in BLOCKED_QUALIFICATION_STAGES_V10:
            result = {
                "allowed": False,
                "executed": False,
                "reason": "UNKNOWN_STAGE",
                "stage": stage,
                "status": STAGE_STATUS_BLOCKED,
            }
            self.attempt_log.append(deepcopy(result))
            return result

        # Keep stage BLOCKED even after an advance attempt.
        self.stages[stage] = STAGE_STATUS_BLOCKED
        result = {
            "allowed": False,
            "executed": False,
            "reason": BLOCK_REASON,
            "stage": stage,
            "label": STAGE_LABELS[stage],
            "status": self.stages[stage],
            "founder_authorization_present": False,
            "formal_walk_forward_executed": False,
            "oos_reservation_created": False,
            "oos_executed": False,
            "strategy_selected": False,
            "strategy_promoted": False,
            "demo_order_count": 0,
        }
        self.attempt_log.append(deepcopy(result))
        return result

    def attempt_all_stages(self) -> dict[str, dict[str, Any]]:
        return {stage: self.attempt_execute_stage(stage) for stage in BLOCKED_QUALIFICATION_STAGES_V10}

    def all_blocked(self) -> bool:
        return all(v == STAGE_STATUS_BLOCKED for v in self.stages.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_order": list(BLOCKED_QUALIFICATION_STAGES_V10),
            "stage_labels": dict(STAGE_LABELS),
            "stages": dict(self.stages),
            "all_stages_blocked": self.all_blocked(),
            "block_reason": BLOCK_REASON,
            "hard_bans": list(HARD_BANS),
            "attempt_count": len(self.attempt_log),
            "attempts": list(self.attempt_log),
        }
