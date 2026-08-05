"""Founder V13-F Qualification Dry-Run Control constants."""
from __future__ import annotations

from pathlib import Path

SCHEMA_ID = "FOUNDER_V13_F_QUALIFICATION_DRY_RUN_CONTROL"
DISCOVERY_BUNDLE_SCHEMA = "NEXUS_DISCOVERY_OUTPUT_BUNDLE_V13"
LANE = "V13-F"
LANE_NAME = "QUALIFICATION_DRY_RUN_CONTROL"
BRANCH = "feature/v13-qualification-dry-run-control"
BASE_COMMIT = "abd2195ef6d79f609dd261b5e9c5402599625a64"

ARTIFACT_REL = Path("artifacts/readiness/immutable/v13_qualification_dry_run_control")
RUNTIME_STATUS_DEFAULT = Path(r"D:\NEXUS_RUNTIME\v13_f_qualification_dryrun_status.json")

INFRA_STATUS_BLOCKED_READY = "BLOCKED_READY"
FORMAL_STATUS_BLOCKED = "BLOCKED"
STAGE_STATUS_BLOCKED = "BLOCKED"
PLAN_STATUS_PLANNED_NOT_EXECUTED = "PLANNED_NOT_EXECUTED"

# Formal stages remain BLOCKED. Plans may be generated; none execute.
FORMAL_STAGES: tuple[str, ...] = (
    "CANDIDATE_FREEZE",
    "DEVELOPMENT_REPLAY",
    "WALK_FORWARD",
    "RISK_REVIEW",
    "OOS_RESERVATION",
    "DEMO_ELIGIBILITY",
)

STAGE_LABELS: dict[str, str] = {
    "CANDIDATE_FREEZE": "Candidate Freeze",
    "DEVELOPMENT_REPLAY": "Development Replay",
    "WALK_FORWARD": "Walk-forward",
    "RISK_REVIEW": "Risk Review",
    "OOS_RESERVATION": "OOS reservation",
    "DEMO_ELIGIBILITY": "Demo eligibility",
}

HARD_BANS: tuple[str, ...] = (
    "no_formal_walk_forward",
    "no_real_oos_reservation",
    "no_real_oos_consumption",
    "no_strategy_selection",
    "no_strategy_promotion",
    "no_demo_orders",
    "no_shadow_orders",
    "no_exchange_writes",
    "no_pr27_merge",
    "no_mainnet",
    "no_real_money",
    "no_profitability_claims",
)

ALLOWED_DISCOVERY_LABELS: tuple[str, ...] = (
    "RESEARCH_SIGNAL_ONLY",
    "RAW_EDGE_PRESENT_BUT_COST_DESTROYED",
    "INSUFFICIENT_SAMPLE",
    "REGIME_FRAGILE",
    "DATA_QUALITY_BLOCKED",
    "DEVELOPMENT_PROMISING_NOT_QUALIFIED",
    "REJECTED",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_qualification/dryrun_v13",
    "backend/nexus_qualification/__init__.py",
    "tools/research/run_qualification_dry_run_control_v13.py",
    "tests/test_qualification_dry_run_control_v13.py",
    "artifacts/readiness/immutable/v13_qualification_dry_run_control",
)

PROHIBITED_PATHS: tuple[str, ...] = (
    "frontend/",
    "btc_bot/frontend/",
    "backend/nexus_demo_execution/",
)

BLOCK_REASON = "STAGE_DEFAULT_BLOCKED_V13_F_DRY_RUN_CONTROL_ONLY"
