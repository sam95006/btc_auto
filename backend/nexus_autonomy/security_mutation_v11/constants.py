"""V11 Security Mutation Red Team — constants and owned-path declarations."""
from __future__ import annotations

SCHEMA = "v11_security_mutation_redteam"
PROGRAM_ID = "NEXUS_V11_SECURITY_MUTATION_REDTEAM"
LANE = "G"
BRANCH = "feature/v11_1-g-ast-mutation-depth"

PASS_RECOMMENDATION = "NEXUS_V11_SECURITY_MUTATION_REDTEAM_PASS"
FAIL_RECOMMENDATION = "NEXUS_V11_SECURITY_MUTATION_REDTEAM_CRITICAL_FINDINGS"
BLOCKED_RECOMMENDATION = "NEXUS_V11_SECURITY_MUTATION_REDTEAM_UNRESOLVED_SURVIVORS"
INVALID_RECOMMENDATION = "NEXUS_V11_SECURITY_MUTATION_REDTEAM_IMPLEMENTATION_INVALID"

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_autonomy/security_mutation_v11/",
    "tools/research/run_security_mutation_redteam_v11.py",
    "tools/ci/scan_security_mutation_v11.py",
    "tools/ci/scan_production_ast_mutation_v11.py",
    "tests/test_security_mutation_redteam_v11.py",
    "tests/test_production_ast_mutation_v11.py",
    "artifacts/readiness/immutable/v11_security_mutation_redteam/",
    "artifacts/readiness/immutable/v11_1_g_ast_mutation/",
)

PROHIBITED_PATHS: tuple[str, ...] = (
    "frontend/",
    "backend/nexus_demo_execution/",
    "G:/",
    "PR26",
)

# Safety-critical subject ids under mutation campaign.
SUBJECT_IDS: tuple[str, ...] = (
    "exchange_write_prevention",
    "risk_limits",
    "idempotency",
    "ledger_hashes",
    "snapshot_recovery",
    "checkpoint_migration",
    "public_private_boundary",
    "demo_mainnet_separation",
    "path_traversal",
    "symlink_escape",
    "secret_redaction",
    "provider_prompt_leakage",
    "unsafe_deserialization",
    "credential_confusion",
    "network_egress",
    "import_graph",
)

REQUIRED_COUNTERS_ZERO: tuple[str, ...] = (
    "exchange_write_attempt_count",
    "secret_leak_count",
    "mainnet_client_created_count",
)

LABEL = "SECURITY_MUTATION_REDTEAM_CONTROL_NOT_REAL_TRADING"
EXECUTION_MODE = "SIMULATED_FAIL_CLOSED_NO_EXCHANGE_WRITE"

# Production modules targeted by real AST mutation (Private Core).
PRODUCTION_MUTATION_TARGETS: tuple[str, ...] = (
    "backend/nexus_autonomy/security_persistence_v1.py",
    "backend/nexus_autonomy/security_credential_boundary_v1.py",
    "backend/nexus_autonomy/security_public_private_v1.py",
    "backend/nexus_autonomy/security_write_traps_v1.py",
)

# R4-listed production AST mutants that MUST be detect-killed (not silent).
PRODUCTION_AST_REQUIRED_DETECT_KILLS: tuple[str, ...] = (
    "persist_scan_secrets_noop",
    "persist_json_accept_scalars",
    "public_assert_schema_noop",
    "public_redact_identity",
    "write_trap_install_noop",
)

# Honesty metrics — wrapper-only PASS is forbidden.
WRAPPER_ONLY_PASS_FORBIDDEN = True
PRODUCTION_AST_SURVIVOR_COUNT_REQUIRED = 0

# H gate PASS ≠ authority remediation (R4 DUPLICATE_GATE_BASELINE_FALSE_CONFIDENCE).
H_GATE_PASS_IS_NOT_AUTHORITY_REMEDIATION = True
DUPLICATE_GATE_BASELINE_FALSE_CONFIDENCE_ACK = True
H_GATE_HONESTY_NOTE = (
    "Lane H CI duplicate-authority gate PASS baselining known competitors does NOT "
    "clear critical multi-authority blockers. Treat H as audit/registry/gate only -- "
    "not runtime authority remediation. C1-C6 own cost/lifecycle/retry/checkpoint/"
    "shim/SCC remediation."
)

HARD_BANS: tuple[str, ...] = (
    "no_exchange_write",
    "no_demo_orders",
    "no_mainnet_client",
    "no_mass_dependency_upgrades",
    "no_mutmut_cosmic_ray_required",
    "no_wrapper_only_pass",
    "no_treat_h_gate_as_authority_remediation",
    "no_reimplement_c1_c6",
)

REMEDIATION_ARTIFACT_REL = "artifacts/readiness/immutable/v11_1_g_ast_mutation"
