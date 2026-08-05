"""R4 Security + Authority review constants."""
from __future__ import annotations

SCHEMA = "v11_review_security_authority"
PROGRAM_ID = "NEXUS_V11_REVIEW_R4_SECURITY_AUTHORITY"
LANE = "R4"
BRANCH = "feature/v11-review-security-authority"
BASE_SHA = "e4f30f9b8abaaade6151a75ef5ac6face53d5135"

ORIGIN_G_BRANCH = "feature/v11-security-mutation-redteam"
ORIGIN_H_BRANCH = "feature/v11-repository-authority-consolidation"
ORIGIN_G_HEAD = "600245a"
ORIGIN_H_HEAD = "bbffc18"

PASS_RECOMMENDATION = "NEXUS_V11_R4_SECURITY_AUTHORITY_PASS"
FAIL_RECOMMENDATION = "NEXUS_V11_R4_SECURITY_AUTHORITY_CRITICAL_FINDINGS"
BLOCKED_RECOMMENDATION = "NEXUS_V11_R4_SECURITY_AUTHORITY_INTEGRATION_BLOCKED"

OWNED_PATHS: tuple[str, ...] = (
    "tools/review/r4_security_authority/",
    "tests/review/test_r4_security_authority_v11.py",
    "artifacts/readiness/immutable/v11_review_security_authority/",
)

PROHIBITED_MUTATION_PATHS: tuple[str, ...] = (
    "backend/nexus_autonomy/security_mutation_v11/",
    "backend/nexus_contracts/",
    "tools/architecture/",
    "frontend/",
    "G:/",
    "PR26",
)

# Production modules targeted by real AST mutation (base-branch Private Core).
PRODUCTION_MUTATION_TARGETS: tuple[str, ...] = (
    "backend/nexus_autonomy/security_persistence_v1.py",
    "backend/nexus_autonomy/security_credential_boundary_v1.py",
    "backend/nexus_autonomy/security_public_private_v1.py",
    "backend/nexus_autonomy/security_write_traps_v1.py",
)

DEFAULT_ORIGIN_G = r"D:\NEXUS_RUNTIME\worktrees\v11_security_mutation"
DEFAULT_ORIGIN_H = r"D:\NEXUS_RUNTIME\worktrees\v11_authority_consolidation"

ARTIFACT_REL = "artifacts/readiness/immutable/v11_review_security_authority"

LABEL = "R4_SECURITY_AUTHORITY_REVIEW_NOT_REAL_TRADING"
EXECUTION_MODE = "SIMULATED_REVIEW_AST_MUTATION_NO_EXCHANGE_WRITE"

REQUIRED_COUNTERS_ZERO: tuple[str, ...] = (
    "exchange_write_attempt_count",
    "secret_leak_count",
    "mainnet_client_created_count",
)
