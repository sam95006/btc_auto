"""Founder V14-H Candidate Triage Control constants."""
from __future__ import annotations

from pathlib import Path

SCHEMA_ID = "FOUNDER_V14_H_CANDIDATE_TRIAGE_CONTROL"
LANE = "V14-H"
LANE_NAME = "CANDIDATE_TRIAGE_CONTROL"
BRANCH = "feature/v14-candidate-triage-control"
BASE_COMMIT = "15ecb7b9524d253ec4f2fb04dc73aa1673ec906a"

ARTIFACT_REL = Path("artifacts/readiness/immutable/v14_candidate_triage")
RUNTIME_STATUS_DEFAULT = Path(r"D:\NEXUS_RUNTIME\v14_h_status.json")

INFRA_STATUS_BLOCKED_READY = "BLOCKED_READY"
TRIAGE_STATUS_READY = "TRIAGE_READY"
FORMAL_STATUS_BLOCKED = "BLOCKED"
PLAN_STATUS_PLANNED_NOT_EXECUTED = "PLANNED_NOT_EXECUTED"

# Allowed triage statuses only. None are qualification claims.
ALLOWED_TRIAGE_STATUSES: tuple[str, ...] = (
    "REJECTED",
    "DATA_BLOCKED",
    "COST_DESTROYED",
    "SAMPLE_BLOCKED",
    "REGIME_FRAGILE",
    "DEVELOPMENT_REVIEW",
    "DEVELOPMENT_PROMISING_NOT_QUALIFIED",
)

# Explicitly forbidden outputs — fail-closed if emitted.
FORBIDDEN_OUTPUT_STATUSES: tuple[str, ...] = (
    "QUALIFIED",
    "PROMOTED",
    "DEMO_READY",
)

# Connection surface identifiers (sibling V14 lanes + V13 Feature Lab / universe).
CONNECTION_SURFACES: tuple[str, ...] = (
    "mechanism_definitions",
    "feature_lab",
    "dynamic_universe",
    "cost_sensitivity",
    "robustness_results",
    "blocked_qualification_planning",
)

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
    "no_qualified_output",
    "no_promoted_output",
    "no_demo_ready_output",
    "no_auto_integrate",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_candidate_triage",
    "tools/research/candidate_triage",
    "tests/candidate_triage",
    "artifacts/readiness/immutable/v14_candidate_triage",
)

PROHIBITED_PATHS: tuple[str, ...] = (
    "frontend/",
    "btc_bot/frontend/",
    "backend/nexus_demo_execution/",
)

EVIDENCE_CLASS = "FIXTURE_AND_DEVELOPMENT_ONLY"
BLOCK_REASON = "FORMAL_QUALIFICATION_BLOCKED_V14_H_TRIAGE_ONLY"

# Priority order for multi-signal collision (most restrictive first).
TRIAGE_PRIORITY: tuple[str, ...] = (
    "DATA_BLOCKED",
    "SAMPLE_BLOCKED",
    "COST_DESTROYED",
    "REGIME_FRAGILE",
    "REJECTED",
    "DEVELOPMENT_REVIEW",
    "DEVELOPMENT_PROMISING_NOT_QUALIFIED",
)
