"""V14-I Universe Lineage and Listing-Bias Red Team — constants."""
from __future__ import annotations

SCHEMA = "v14_universe_redteam"
PROGRAM_ID = "NEXUS_V14_UNIVERSE_LINEAGE_REDTEAM"
LANE = "V14-I"
BRANCH = "feature/v14-universe-lineage-redteam"
BASE_HEAD = "15ecb7b9524d253ec4f2fb04dc73aa1673ec906a"

PASS_RECOMMENDATION = "NEXUS_V14_UNIVERSE_LINEAGE_REDTEAM_PASS"
FAIL_RECOMMENDATION = "NEXUS_V14_UNIVERSE_LINEAGE_REDTEAM_CRITICAL_FINDINGS"
BLOCKED_RECOMMENDATION = "NEXUS_V14_UNIVERSE_LINEAGE_REDTEAM_UNRESOLVED_SURVIVORS"
INVALID_RECOMMENDATION = "NEXUS_V14_UNIVERSE_LINEAGE_REDTEAM_IMPLEMENTATION_INVALID"

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_universe_redteam/",
    "tools/research/universe_redteam/",
    "tests/universe_redteam/",
    "artifacts/readiness/immutable/v14_universe_redteam/",
)

PROHIBITED_PATHS: tuple[str, ...] = (
    "frontend/",
    "backend/nexus_demo_execution/",
    "G:/",
    "PR27",
    "deploy/",
)

HARD_BANS: tuple[str, ...] = (
    "no_auto_integration_into_PR27",
    "no_demo_orders",
    "no_exchange_write",
    "no_mainnet_client",
    "no_merge",
    "no_deploy",
    "no_platform_blocked_mutation_as_pass",
    "no_today_universe_for_past",
    "no_fixture_as_real_performance",
    "no_survivorship_only_reconstruction",
    "no_silent_rename_without_lineage",
)

ATTACK_SCENARIO_IDS: tuple[str, ...] = (
    "survivorship_bias",
    "listing_date_leakage",
    "delisting_leakage",
    "rename_leakage",
    "contract_spec_changes",
    "today_universe_substitution",
    "future_liquidity_leakage",
    "future_funding_availability",
    "mapping_drift",
    "min_notional_drift",
)

FIXTURE_IDS: tuple[str, ...] = (
    "property_fuzz_universe_checksums",
    "schema_mutation_lineage",
    "era_comparison_stability",
    "adversarial_suite_reuse",
)

LABEL = "UNIVERSE_LINEAGE_REDTEAM_CONTROL_NOT_REAL_TRADING"
EXECUTION_MODE = "SIMULATED_FAIL_CLOSED_NO_EXCHANGE_WRITE"
EVIDENCE_CLASS = "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE"

RUNTIME_MATRIX_PATH = "D:\\NEXUS_RUNTIME\\v14_readiness_matrix.json"
RUNTIME_LANE_STATUS_PATH = "D:\\NEXUS_RUNTIME\\v14_i_status.json"

STRUCTURAL_BLOCKERS: tuple[str, ...] = (
    "V14_lanes_incomplete",
    "no_qualified_strategy_edge",
    "event_study_NOT_READY",
    "PR27_draft_unmerged",
    "auto_integration_forbidden",
    "qualification_ready_count_must_remain_0",
    "oos_executed_must_remain_false",
    "microstructure_14d_capture_in_progress",
)
