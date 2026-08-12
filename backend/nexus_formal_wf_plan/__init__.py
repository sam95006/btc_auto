"""V15-F Formal Walk-Forward Plan Compiler — Founder-private proof surface.

Build formal Walk-forward plans (training/validation/embargo/purge/freezes/
thresholds/requirements) but NEVER execute them.

Status is always PLAN_READY_EXECUTION_BLOCKED.
formal_walk_forward_executed=false always.
"""
from __future__ import annotations

from backend.nexus_formal_wf_plan.adversarial import run_two_pass_campaign
from backend.nexus_formal_wf_plan.campaign import run_campaign_and_write, write_immutable_artifacts
from backend.nexus_formal_wf_plan.compiler import (
    FormalWalkForwardPlanCompiler,
    compile_formal_wf_plan,
    compile_formal_wf_plans,
)
from backend.nexus_formal_wf_plan.constants import (
    HARD_BAN_FLAGS,
    HARD_BANS,
    LANE,
    PLAN_DIMENSIONS,
    PLAN_STATUS_READY_EXECUTION_BLOCKED,
    SCHEMA_ID,
)
from backend.nexus_formal_wf_plan.execution_gate import FormalWalkForwardExecutionGate
from backend.nexus_formal_wf_plan.hard_bans import HardBanViolation, refuse_formal_walk_forward_execution

__all__ = [
    "HARD_BAN_FLAGS",
    "HARD_BANS",
    "LANE",
    "PLAN_DIMENSIONS",
    "PLAN_STATUS_READY_EXECUTION_BLOCKED",
    "SCHEMA_ID",
    "FormalWalkForwardExecutionGate",
    "FormalWalkForwardPlanCompiler",
    "HardBanViolation",
    "compile_formal_wf_plan",
    "compile_formal_wf_plans",
    "refuse_formal_walk_forward_execution",
    "run_campaign_and_write",
    "run_two_pass_campaign",
    "write_immutable_artifacts",
]
