"""V14-L Research Security and False-Pass Red Team — constants."""
from __future__ import annotations

SCHEMA = "v14_research_redteam"
PROGRAM_ID = "NEXUS_V14_RESEARCH_SECURITY_REDTEAM"
LANE = "V14-L"
BRANCH = "feature/v14-research-security-redteam"
BASE_HEAD = "15ecb7b9524d253ec4f2fb04dc73aa1673ec906a"

PASS_RECOMMENDATION = "NEXUS_V14_RESEARCH_SECURITY_REDTEAM_PASS"
FAIL_RECOMMENDATION = "NEXUS_V14_RESEARCH_SECURITY_REDTEAM_CRITICAL_FINDINGS"
BLOCKED_RECOMMENDATION = "NEXUS_V14_RESEARCH_SECURITY_REDTEAM_UNRESOLVED_SURVIVORS"
INVALID_RECOMMENDATION = "NEXUS_V14_RESEARCH_SECURITY_REDTEAM_IMPLEMENTATION_INVALID"

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_research_redteam/",
    "tools/research/redteam_v14/",
    "tests/redteam_v14/",
    "artifacts/readiness/immutable/v14_research_redteam/",
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
    "no_fixture_as_real_performance",
    "no_provider_failure_as_quality_failure",
    "no_surviving_critical_mutation_as_pass",
)

ATTACK_SCENARIO_IDS: tuple[str, ...] = (
    "future_data_leakage",
    "oos_consumption",
    "fabricated_universe",
    "counter_inflation",
    "result_cherry_picking",
    "candidate_relabeling",
    "cost_omission",
    "fixture_as_real",
    "provider_failure_as_quality_failure",
    "founder_auth_spoof",
    "exchange_write_bypass",
    "mainnet_profile_confusion",
    "secret_leakage",
    "checkpoint_rollback",
    "ledger_fork",
)

FIXTURE_IDS: tuple[str, ...] = (
    "property_fuzz_research_seals",
    "schema_mutation_result",
    "result_mutation",
    "checkpoint_mutation",
    "ledger_fork",
)

PRODUCTION_MUTATION_TARGETS: tuple[str, ...] = (
    "backend/nexus_autonomy/security_persistence_v1.py",
    "backend/nexus_autonomy/security_write_traps_v1.py",
    "backend/nexus_autonomy/security_public_private_v1.py",
    "backend/nexus_autonomy/security_credential_boundary_v1.py",
)

PRODUCTION_AST_REQUIRED_DETECT_KILLS: tuple[str, ...] = (
    "persist_scan_secrets_noop",
    "persist_json_accept_scalars",
    "public_assert_schema_noop",
    "public_redact_identity",
    "write_trap_install_noop",
)

LABEL = "RESEARCH_SECURITY_REDTEAM_CONTROL_NOT_REAL_TRADING"
EXECUTION_MODE = "SIMULATED_FAIL_CLOSED_NO_EXCHANGE_WRITE"

RUNTIME_MATRIX_PATH = "D:\\NEXUS_RUNTIME\\v14_readiness_matrix.json"
RUNTIME_LANE_STATUS_PATH = "D:\\NEXUS_RUNTIME\\v14_l_status.json"

STRUCTURAL_BLOCKERS: tuple[str, ...] = (
    "V14_lanes_incomplete",
    "no_qualified_strategy_edge",
    "event_study_NOT_READY",
    "PR27_draft_unmerged",
    "auto_integration_forbidden",
    "qualification_ready_count_must_remain_0",
    "oos_executed_must_remain_false",
)
