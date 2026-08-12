"""Founder V15-F Formal Walk-Forward Plan Compiler constants."""
from __future__ import annotations

from pathlib import Path

SCHEMA_ID = "FOUNDER_V15_F_FORMAL_WALK_FORWARD_PLAN_COMPILER"
SCHEMA_VERSION = 1
LANE = "V15-F"
LANE_NAME = "FORMAL_WALK_FORWARD_PLAN_COMPILER"
BRANCH = "feature/v15-formal-wf-plan-compiler"
BASE_COMMIT = "a7c14d9e9004e0e3a6399424fa3375fdea17e367"

ARTIFACT_REL = Path("artifacts/readiness/immutable/v15_formal_wf_plan")

# Plan may be compiled; formal execution remains blocked forever in this lane.
PLAN_STATUS_READY_EXECUTION_BLOCKED = "PLAN_READY_EXECUTION_BLOCKED"
EXECUTION_STATUS_BLOCKED = "BLOCKED"
BLOCK_REASON = "FORMAL_WALK_FORWARD_EXECUTION_BANNED_V15_F"

HARD_BANS: tuple[str, ...] = (
    "no_formal_walk_forward_execution",
    "no_oos_execution",
    "no_oos_reservation",
    "no_oos_consumption",
    "no_demo_orders",
    "no_shadow_orders",
    "no_exchange_writes",
    "no_mainnet",
    "no_real_money",
    "no_strategy_selection",
    "no_strategy_promotion",
    "no_profitability_claims",
    "no_fabricated_edge",
    "no_fabricated_ai_learning",
    "no_pr_merge",
    "no_deployment",
    "no_public_product_changes",
)

# Required plan surface dimensions (directive inventory).
PLAN_DIMENSIONS: tuple[str, ...] = (
    "training_windows",
    "validation_windows",
    "embargo",
    "purge_intervals",
    "parameter_freeze_rules",
    "candidate_freeze_rules",
    "cost_version_freeze",
    "code_version_freeze",
    "dataset_freeze",
    "failure_thresholds",
    "minimum_sample_sizes",
    "regime_requirements",
    "symbol_requirements",
)

DEFAULT_TRAINING_DAYS = 90
DEFAULT_VALIDATION_DAYS = 30
DEFAULT_STEP_DAYS = 30
DEFAULT_EMBARGO_DAYS = 2
DEFAULT_PURGE_DAYS = 1
DEFAULT_MIN_TRAIN_BARS = 500
DEFAULT_MIN_VAL_BARS = 100
DEFAULT_MAX_FOLDS = 8

MS_PER_DAY = 86_400_000

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_formal_wf_plan",
    "tools/research/formal_wf_plan",
    "tools/research/run_formal_wf_plan_compiler_v15f.py",
    "tests/test_formal_wf_plan_compiler_v15f.py",
    "artifacts/readiness/immutable/v15_formal_wf_plan",
)

PROHIBITED_PATHS: tuple[str, ...] = (
    "frontend/",
    "btc_bot/frontend/",
    "backend/nexus_demo_execution/",
)

HARD_BAN_FLAGS: dict[str, bool | int] = {
    "formal_walk_forward_executed": False,
    "oos_reservation_created": False,
    "oos_executed": False,
    "oos_consumed": False,
    "strategy_selected": False,
    "strategy_promoted": False,
    "demo_order_count": 0,
    "shadow_order_count": 0,
    "exchange_write_attempt_count": 0,
    "mainnet": False,
    "real_money": False,
    "Founder_authorization_present": False,
    "profitability_claim": False,
    "qualification_ready_count": 0,
}
