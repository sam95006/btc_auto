"""V11 Security Mutation Red Team — constants and owned-path declarations."""
from __future__ import annotations

SCHEMA = "v11_security_mutation_redteam"
PROGRAM_ID = "NEXUS_V11_SECURITY_MUTATION_REDTEAM"
LANE = "G"
BRANCH = "feature/v11-security-mutation-redteam"

PASS_RECOMMENDATION = "NEXUS_V11_SECURITY_MUTATION_REDTEAM_PASS"
FAIL_RECOMMENDATION = "NEXUS_V11_SECURITY_MUTATION_REDTEAM_CRITICAL_FINDINGS"
BLOCKED_RECOMMENDATION = "NEXUS_V11_SECURITY_MUTATION_REDTEAM_UNRESOLVED_SURVIVORS"
INVALID_RECOMMENDATION = "NEXUS_V11_SECURITY_MUTATION_REDTEAM_IMPLEMENTATION_INVALID"

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_autonomy/security_mutation_v11/",
    "tools/research/run_security_mutation_redteam_v11.py",
    "tools/ci/scan_security_mutation_v11.py",
    "tests/test_security_mutation_redteam_v11.py",
    "artifacts/readiness/immutable/v11_security_mutation_redteam/",
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
