"""V15-L Private Core Final False-Pass Red Team — constants."""
from __future__ import annotations

SCHEMA = "v15_private_core_redteam"
PROGRAM_ID = "NEXUS_V15_PRIVATE_CORE_FINAL_FALSE_PASS_REDTEAM"
LANE = "V15-L"
BRANCH = "feature/v15-private-core-final-redteam"
BASE_HEAD = "a7c14d9e9004e0e3a6399424fa3375fdea17e367"

PASS_RECOMMENDATION = "NEXUS_V15_PRIVATE_CORE_FINAL_REDTEAM_PASS"
FAIL_RECOMMENDATION = "NEXUS_V15_PRIVATE_CORE_FINAL_REDTEAM_CRITICAL_FINDINGS"
BLOCKED_RECOMMENDATION = "NEXUS_V15_PRIVATE_CORE_FINAL_REDTEAM_UNRESOLVED_SURVIVORS"
INVALID_RECOMMENDATION = "NEXUS_V15_PRIVATE_CORE_FINAL_REDTEAM_IMPLEMENTATION_INVALID"

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_private_core_redteam/",
    "tools/research/redteam_v15/",
    "tests/redteam_v15/",
    "artifacts/readiness/immutable/v15_private_core_redteam/",
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
    "no_merge_pr26_pr27",
    "no_demo_orders",
    "no_shadow_orders",
    "no_exchange_write",
    "no_mainnet_client",
    "no_real_money",
    "no_real_oos_reservation_execution_consumption",
    "no_formal_walkforward",
    "no_deploy",
    "no_platform_blocked_mutation_as_pass",
    "no_fixture_as_real_performance",
    "no_provider_capacity_as_quality",
    "no_lesson_before_reflection",
    "no_risk_bypass",
    "no_duplicate_lifecycle_objects",
    "no_surviving_critical_mutation_as_pass",
)

ATTACK_SCENARIO_IDS: tuple[str, ...] = (
    "future_data_leakage",
    "development_oos_confusion",
    "fabricated_universe",
    "cost_omission",
    "result_cherry_picking",
    "candidate_relabeling",
    "counter_inflation",
    "checkpoint_rollback",
    "ledger_fork",
    "duplicate_lifecycle",
    "risk_bypass",
    "lesson_before_reflection",
    "capacity_as_quality",
    "founder_auth_spoof",
    "exchange_write_bypass",
    "mainnet_profile_confusion",
    "secret_leakage",
)

FIXTURE_IDS: tuple[str, ...] = (
    "property_fuzz_research_seals",
    "schema_mutation_result",
    "result_mutation",
    "checkpoint_mutation",
    "ledger_mutation",
    "concurrency_fuzz",
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

LABEL = "PRIVATE_CORE_FINAL_REDTEAM_CONTROL_NOT_REAL_TRADING"
EXECUTION_MODE = "SIMULATED_FAIL_CLOSED_NO_EXCHANGE_WRITE"

STRUCTURAL_BLOCKERS: tuple[str, ...] = (
    "V15_lanes_incomplete",
    "no_qualified_strategy_edge",
    "PR27_draft_unmerged",
    "auto_integration_forbidden",
    "qualification_ready_count_must_remain_0",
    "oos_executed_must_remain_false",
    "critical_survivors_block_v15_readiness",
)
