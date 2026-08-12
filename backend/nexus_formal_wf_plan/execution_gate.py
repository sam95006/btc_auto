"""Execution gate — formal Walk-forward may never run in V15-F."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_formal_wf_plan.constants import (
    BLOCK_REASON,
    EXECUTION_STATUS_BLOCKED,
    PLAN_STATUS_READY_EXECUTION_BLOCKED,
)
from backend.nexus_formal_wf_plan.hard_bans import (
    HardBanViolation,
    canonical_hard_ban_flags,
    refuse_formal_walk_forward_execution,
)


class FormalWalkForwardExecutionGate:
    """Fail-closed gate: compile allowed, execution always refused."""

    def __init__(self) -> None:
        self.attempt_log: list[dict[str, Any]] = []

    def attempt_execute_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        plan_id = plan.get("plan_id")
        result = {
            "allowed": False,
            "executed": False,
            "plan_id": plan_id,
            "candidate_id": plan.get("candidate_id"),
            "reason": BLOCK_REASON,
            "status": EXECUTION_STATUS_BLOCKED,
            "plan_status": PLAN_STATUS_READY_EXECUTION_BLOCKED,
            "formal_walk_forward_executed": False,
            **canonical_hard_ban_flags(),
        }
        self.attempt_log.append(deepcopy(result))
        return result

    def attempt_execute_fold(self, plan: dict[str, Any], fold_id: str) -> dict[str, Any]:
        result = {
            "allowed": False,
            "executed": False,
            "plan_id": plan.get("plan_id"),
            "fold_id": fold_id,
            "reason": BLOCK_REASON,
            "status": EXECUTION_STATUS_BLOCKED,
            "formal_walk_forward_executed": False,
        }
        self.attempt_log.append(deepcopy(result))
        return result

    def force_execute_or_raise(self, plan: dict[str, Any]) -> None:
        """Adversarial helper: any force-execute path must raise."""
        refuse_formal_walk_forward_execution()

    def assert_never_executed(self, plan: dict[str, Any]) -> None:
        if plan.get("formal_walk_forward_executed") is not False:
            raise HardBanViolation("plan formal_walk_forward_executed must be false")
        if plan.get("status") != PLAN_STATUS_READY_EXECUTION_BLOCKED:
            raise HardBanViolation("plan status drift")
        if plan.get("executed") is True:
            raise HardBanViolation("plan executed flag set")

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_reason": BLOCK_REASON,
            "execution_status": EXECUTION_STATUS_BLOCKED,
            "attempt_count": len(self.attempt_log),
            "attempts": list(self.attempt_log),
            "all_attempts_refused": all(
                (not a.get("allowed")) and (not a.get("executed")) for a in self.attempt_log
            ),
            "formal_walk_forward_executed": False,
        }
