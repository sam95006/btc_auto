"""V16-F Lesson Validation Firewall — constants and hard bans.

Promotion pipeline mechanics only (interfaces / fixtures / safety gates).
This window NEVER marks a real Lesson ACTIVE.
"""
from __future__ import annotations

from pathlib import Path

SCHEMA_ID = "FOUNDER_V16_F_LESSON_VALIDATION_FIREWALL"
LANE = "V16-F"
LANE_NAME = "LESSON_VALIDATION_FIREWALL"
BRANCH = "feature/v16-lesson-validation-firewall"
BASE_COMMIT = "f01407e5d7c7e4c00e0eb1616dc5ef74d91a58b5"
PACKAGE = "backend.nexus_lesson_validation_firewall"

ARTIFACT_REL = Path("artifacts/readiness/immutable/v16_lesson_validation_firewall")

# Exact promotion pipeline (ordered).
PROMOTION_STATES: tuple[str, ...] = (
    "CANDIDATE",
    "REPLAY_VALIDATED",
    "WALK_FORWARD_PENDING",
    "OOS_PENDING",
    "SHADOW_PENDING",
    "DEMO_PENDING",
    "ACTIVE",
    "DEGRADED",
    "RETIRED",
)

# Forward edges only (consecutive + ACTIVE→DEGRADED→RETIRED).
FORWARD_TRANSITIONS: dict[str, frozenset[str]] = {
    "CANDIDATE": frozenset({"REPLAY_VALIDATED", "RETIRED"}),
    "REPLAY_VALIDATED": frozenset({"WALK_FORWARD_PENDING", "RETIRED"}),
    "WALK_FORWARD_PENDING": frozenset({"OOS_PENDING", "RETIRED"}),
    "OOS_PENDING": frozenset({"SHADOW_PENDING", "RETIRED"}),
    "SHADOW_PENDING": frozenset({"DEMO_PENDING", "RETIRED"}),
    "DEMO_PENDING": frozenset({"ACTIVE", "RETIRED"}),
    "ACTIVE": frozenset({"DEGRADED", "RETIRED"}),
    "DEGRADED": frozenset({"RETIRED"}),
    "RETIRED": frozenset(),
}

EVIDENCE_CLASS_FIXTURE = "FIXTURE_MECHANICS_ONLY"
EVIDENCE_CLASS_REAL = "REAL_LESSON"

INFRA_STATUS = "FIREWALL_READY_ACTIVE_BLOCKED"
CONTROL_STATUS = "SAFETY_GATES_ENFORCED"

# SoT blockers for this window (fail-closed).
SOT_V2_3_COMPLETE = False
SOT_V2_3_TERMINAL = "INCOMPLETE_PROVIDER_CAPACITY"
SOT_FORMAL_WF = False
SOT_OOS = False
SOT_LESSON_PREVENTION = "BLOCKED"
SOT_REAL_ACTIVE_ALLOWED = False

HARD_BANS: tuple[str, ...] = (
    "no_real_lesson_active",
    "no_ai_self_promote",
    "no_favorable_only_cherry_picking",
    "no_stage_skip",
    "no_formal_walk_forward_execution",
    "no_oos_execution",
    "no_real_lesson_prevention_while_v23_incomplete",
    "no_production_mutation",
    "no_demo_orders",
    "no_shadow_orders",
    "no_exchange_writes",
    "no_mainnet",
    "no_real_money",
    "no_pr27_merge",
    "no_auto_integrate",
    "no_profitability_claim",
    "no_status_json_report",
    "no_immutable_record_rewrite",
    "no_catastrophic_forgetting",
    "no_contradictory_evidence_ignore",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_lesson_validation_firewall/",
    "tools/research/lesson_validation_firewall/",
    "tests/lesson_validation_firewall/",
)

PROHIBITED_PATHS: tuple[str, ...] = (
    "frontend/",
    "backend/nexus_demo_execution/",
    "backend/api/",
)

REQUIRED_FALSE_FLAGS: tuple[str, ...] = (
    "real_lesson_active",
    "formal_walk_forward_executed",
    "oos_executed",
    "production_mutated",
    "ai_self_promoted",
    "cherry_picked",
    "demo_order_count_nonzero",
    "exchange_write_attempted",
    "mainnet",
    "real_money",
    "pr27_merged",
    "auto_integrated",
)

FORBIDDEN_STATUS_JSON_SUFFIX = "_status.json"
FORBIDDEN_STATUS_BASENAMES: tuple[str, ...] = (
    "status.json",
    "v16_f_status.json",
    "lesson_firewall_status.json",
    "lane_status.json",
    "report.json",
)

BLOCK_REASONS_ACTIVE: tuple[str, ...] = (
    "V2_3_INCOMPLETE",
    "FORMAL_WF_FALSE",
    "OOS_FALSE",
    "LESSON_PREVENTION_BLOCKED",
)

FOUNDER_AUTH_SCOPE = "founder_v16_f_lesson_validation_firewall"
DEFAULT_TTL_SECONDS = 86_400
FIXTURE_LABEL = "FIXTURE_NOT_REAL_LESSON_PROMOTION"
REAL_LABEL = "REAL_LESSON_PROMOTION_BLOCKED_THIS_WINDOW"
