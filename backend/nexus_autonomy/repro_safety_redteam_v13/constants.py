"""V13-H Reproducibility and Safety Red Team — constants."""
from __future__ import annotations

SCHEMA = "v13_repro_safety_redteam"
PROGRAM_ID = "NEXUS_V13_REPRO_SAFETY_REDTEAM"
LANE = "V13-H"
BRANCH = "feature/v13-reproducibility-safety-redteam"
BASE_HEAD = "abd2195ef6d79f609dd261b5e9c5402599625a64"

PASS_RECOMMENDATION = "NEXUS_V13_REPRO_SAFETY_REDTEAM_PASS"
FAIL_RECOMMENDATION = "NEXUS_V13_REPRO_SAFETY_REDTEAM_CRITICAL_FINDINGS"
BLOCKED_RECOMMENDATION = "NEXUS_V13_REPRO_SAFETY_REDTEAM_UNRESOLVED_SURVIVORS"
INVALID_RECOMMENDATION = "NEXUS_V13_REPRO_SAFETY_REDTEAM_IMPLEMENTATION_INVALID"

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_autonomy/repro_safety_redteam_v13/",
    "tools/research/run_repro_safety_redteam_v13.py",
    "tests/test_repro_safety_redteam_v13.py",
    "artifacts/readiness/immutable/v13_repro_safety_redteam/",
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
)

ATTACK_SCENARIO_IDS: tuple[str, ...] = (
    "pit_lineage_tamper",
    "decision_evidence_hash_mismatch",
    "cost_version_divergence",
    "risk_version_divergence",
    "checkpoint_version_tamper",
    "provider_model_provenance_spoof",
    "dynamic_universe_reconstruction_drift",
    "future_data_exclusion_bypass",
    "oos_non_consumption_violation",
    "founder_auth_spoof",
    "exchange_write_trap",
    "mainnet_profile_separation",
    "secret_redaction_leak",
)

FIXTURE_IDS: tuple[str, ...] = (
    "property_fuzz_evidence_hashes",
    "schema_mutation_envelope",
    "checkpoint_mutation",
    "ledger_fork",
)

# Production modules targeted by real AST mutation (sandbox only).
PRODUCTION_MUTATION_TARGETS: tuple[str, ...] = (
    "backend/nexus_autonomy/security_persistence_v1.py",
    "backend/nexus_autonomy/security_write_traps_v1.py",
    "backend/nexus_autonomy/security_public_private_v1.py",
    "backend/nexus_autonomy/security_credential_boundary_v1.py",
)

# Required detect-kills; platform-blocked must NOT be counted as PASS.
PRODUCTION_AST_REQUIRED_DETECT_KILLS: tuple[str, ...] = (
    "persist_scan_secrets_noop",
    "persist_json_accept_scalars",
    "public_assert_schema_noop",
    "public_redact_identity",
    "write_trap_install_noop",
)

LABEL = "REPRO_SAFETY_REDTEAM_CONTROL_NOT_REAL_TRADING"
EXECUTION_MODE = "SIMULATED_FAIL_CLOSED_NO_EXCHANGE_WRITE"

RUNTIME_MATRIX_PATH = "D:\\NEXUS_RUNTIME\\v13_readiness_matrix.json"
RUNTIME_LANE_STATUS_PATH = "D:\\NEXUS_RUNTIME\\v13_h_repro_safety_status.json"

# Structural blockers never cleared by this lane alone.
STRUCTURAL_BLOCKERS: tuple[str, ...] = (
    "V2.3_incomplete",
    "microstructure_14d_data",
    "no_qualified_strategy_edge",
    "event_study_NOT_READY",
    "PR27_draft_unmerged",
    "auto_integration_forbidden",
    "qualification_ready_count_must_remain_0",
)
