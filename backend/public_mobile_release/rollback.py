"""Release rollback helpers — flag kill-switch first; store upload banned."""

from __future__ import annotations

from dataclasses import dataclass, field


FORBIDDEN_ROLLBACK_ACTIONS = frozenset(
    {
        "upload_to_app_store",
        "upload_to_play_store",
        "fastlane_deliver",
        "promote_production_track",
    }
)


@dataclass
class RollbackPlan:
    steps: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.rejected


def build_rollback_plan(requested_actions: list[str]) -> RollbackPlan:
    plan = RollbackPlan()
    # Always prefer remote flag disable first
    plan.steps.append("disable_regional_membership_signup")
    plan.steps.append("freeze_billing_verify_endpoint")
    plan.steps.append("pause_deletion_purge_worker")
    for action in requested_actions:
        if action in FORBIDDEN_ROLLBACK_ACTIONS:
            plan.rejected.append(action)
            continue
        plan.steps.append(action)
    plan.steps.append("verify_hard_ban_gate")
    return plan
