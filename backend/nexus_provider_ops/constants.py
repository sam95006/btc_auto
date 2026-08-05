"""Founder-private Provider Completion Ops V12-C — constants and hard bans."""
from __future__ import annotations

from backend.nexus_ai.profiles import (
    DEFAULT_BUCKET_PARAMS,
    GROQ_REFLECTION_REASONER,
    SAMBANOVA_INDEPENDENT_CRITIC,
)

SCHEMA = "v12_provider_completion_ops"
SCHEMA_STATUS = "v12_provider_completion_ops_status"
SCHEMA_SECRET_SCAN = "v12_provider_completion_ops_secret_scan"
SCHEMA_QUEUE_HEALTH = "v12_provider_queue_health"
SCHEMA_RETRY_AFTER = "v12_provider_retry_after_obs"
SCHEMA_CAPACITY = "v12_provider_capacity_windows"
SCHEMA_CHECKPOINT = "v12_provider_checkpoint_safety"
SCHEMA_DEDUPE = "v12_provider_completed_case_dedupe"
SCHEMA_MANUAL = "v12_provider_manual_control"
SCHEMA_BOUNDARY = "v12_provider_resume_boundary"
SCHEMA_CYCLE = "v12_provider_ops_cycle"

PACKAGE = "backend.nexus_provider_ops"
LANE = "V12-C"
LANE_NAME = "PROVIDER_COMPLETION_OPS"
BRANCH = "feature/v12-provider-completion-ops"
ARTIFACT_REL = "artifacts/readiness/immutable/v12_provider_completion_ops"
BASE_COMMIT = "e4e96299840da2e5152cf2850135cebc67d66cd0"

# Real checkpoint SoT remains incomplete — ops design around this truth.
# Never claim V2.3 complete from these counts.
SOT_GROQ_SUCCESS = 53
SOT_GROQ_PENDING = 27
SOT_SAMBANOVA_SUCCESS = 16
SOT_SAMBANOVA_PENDING = 10
SOT_CASE_COUNT = 80
SOT_TERMINAL_STATUS = "INCOMPLETE_PROVIDER_CAPACITY"
SOT_V2_3_COMPLETE = False

PROVIDER_LANES: tuple[str, ...] = (
    GROQ_REFLECTION_REASONER,
    SAMBANOVA_INDEPENDENT_CRITIC,
)

# Local Coordinator is the ONLY owner of real Provider resume.
REAL_RESUME_OWNER = "local_Coordinator"
OPS_ROLE = "observability_and_manual_control_only"

HARD_BANS: tuple[str, ...] = (
    "no_real_provider_resume_ownership_theft",
    "no_secret_logging",
    "no_demo_exchange",
    "no_pr27_merge",
    "no_v2_3_complete_claim",
    "no_exchange_writes",
    "no_mainnet_real_money",
    "no_public_product_surface",
)

FORBIDDEN_LOG_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "password",
        "token",
        "private_key",
        "authorization",
        "raw_prompt",
        "raw_response",
        "bybit_api_key",
        "bybit_api_secret",
        "account_balance",
        "wallet_address",
        "strategy_parameters",
    }
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_provider_ops",
    "tools/research/run_provider_completion_ops_v12.py",
    "tests/test_provider_completion_ops_v12.py",
    ARTIFACT_REL,
)

PROHIBITED_PATHS_UNTOUCHED: tuple[str, ...] = (
    "frontend",
    "backend/nexus_demo_execution",
    "backend/api",
    "other_v12_lane_owned_paths",
    "pr27_merge_surfaces",
)

# Re-export bucket defaults for capacity windows.
BUCKET_PARAMS = DEFAULT_BUCKET_PARAMS
