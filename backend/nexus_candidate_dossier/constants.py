"""Founder V15-E Candidate Dossier Builder constants."""
from __future__ import annotations

from pathlib import Path

SCHEMA_ID = "FOUNDER_V15_E_CANDIDATE_DOSSIER_BUILDER"
LANE = "V15-E"
LANE_NAME = "CANDIDATE_DOSSIER_BUILDER"
BRANCH = "feature/v15-candidate-dossier-builder"
BASE_COMMIT = "a7c14d9e9004e0e3a6399424fa3375fdea17e367"

ARTIFACT_REL = Path("artifacts/readiness/immutable/v15_candidate_dossier")

INFRA_STATUS_BLOCKED_READY = "BLOCKED_READY"
DOSSIER_BUILDER_STATUS = "DOSSIER_BUILDER_READY"
FORMAL_STATUS_BLOCKED = "BLOCKED"

# Ceiling: dossier status may not exceed these development labels.
ALLOWED_DOSSIER_STATUSES: tuple[str, ...] = (
    "DEVELOPMENT_REVIEW",
    "DEVELOPMENT_PROMISING_NOT_QUALIFIED",
)

FORBIDDEN_OUTPUT_STATUSES: tuple[str, ...] = (
    "QUALIFIED",
    "PROMOTED",
    "DEMO_READY",
    "WALK_FORWARD_READY",
    "OOS_READY",
)

REQUIRED_DOSSIER_FIELDS: tuple[str, ...] = (
    "semantic_mechanism",
    "economic_rationale",
    "data_lineage",
    "universe_checksum",
    "feature_version",
    "code_checksum",
    "parameter_checksum",
    "cost_version",
    "risk_version",
    "execution_version",
    "development_intervals",
    "failed_sibling_experiments",
    "regime_breakdown",
    "symbol_breakdown",
    "cost_breakdown",
    "capacity_assumptions",
    "known_failure_conditions",
    "multiple_testing_status",
    "remaining_blockers",
    "dossier_status",
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
    "no_status_json_lane_reports",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_candidate_dossier",
    "tools/research/candidate_dossier",
    "tests/candidate_dossier",
    "artifacts/readiness/immutable/v15_candidate_dossier",
)

PROHIBITED_PATHS: tuple[str, ...] = (
    "frontend/",
    "btc_bot/frontend/",
    "backend/nexus_demo_execution/",
)

EVIDENCE_CLASS = "FIXTURE_AND_DEVELOPMENT_ONLY"
BLOCK_REASON = "FORMAL_QUALIFICATION_BLOCKED_V15_E_DOSSIER_ONLY"

FEATURE_VERSION_DEFAULT = "v15_e_feature_surface_1"
COST_VERSION_DEFAULT = "canonical_cost_model_v11_1"
RISK_VERSION_DEFAULT = "deterministic_risk_gate_v1"
EXECUTION_VERSION_DEFAULT = "autonomous_execution_simulator_v1_1"
CODE_SURFACE_DEFAULT = "backend.nexus_candidate_dossier"
PARAMETER_SURFACE_DEFAULT = "v15_e_development_params_1"
