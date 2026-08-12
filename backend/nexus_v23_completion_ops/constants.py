"""Founder-private V13-B Reflection V2.3 Completion Ops — constants and hard bans."""
from __future__ import annotations

from backend.nexus_ai.profiles import (
    DEFAULT_BUCKET_PARAMS,
    GROQ_REFLECTION_REASONER,
    SAMBANOVA_INDEPENDENT_CRITIC,
)

SCHEMA = "v13_reflection_v23_completion_ops"
SCHEMA_STATUS = "v13_b_reflection_completion_status"
SCHEMA_SECRET_SCAN = "v13_v23_completion_ops_secret_scan"
SCHEMA_PREFLIGHT = "v13_v23_provider_preflight"
SCHEMA_QUEUE = "v13_v23_queue_health"
SCHEMA_RETRY_QUOTA = "v13_v23_retry_quota_obs"
SCHEMA_WINDOWS = "v13_v23_provider_windows"
SCHEMA_PAUSE = "v13_v23_safe_pause_resume"
SCHEMA_ATOMIC = "v13_v23_atomic_checkpoint"
SCHEMA_COUNTERS = "v13_v23_semantic_counters"
SCHEMA_DEDUPE = "v13_v23_completed_case_dedupe"
SCHEMA_CRITIC = "v13_v23_critic_ordering"
SCHEMA_TERMINAL = "v13_v23_terminal_denominator"
SCHEMA_CAPACITY = "v13_v23_capacity_status"
SCHEMA_GATES = "v13_v23_lesson_quality_gates"
SCHEMA_BOUNDARY = "v13_v23_resume_boundary"
SCHEMA_CYCLE = "v13_v23_completion_ops_cycle"

PACKAGE = "backend.nexus_v23_completion_ops"
LANE = "V13-B"
LANE_NAME = "REFLECTION_V23_COMPLETION_OPS"
BRANCH = "feature/v13-reflection-v23-completion-ops"
ARTIFACT_REL = "artifacts/readiness/immutable/v13_reflection_v23_completion_ops"
BASE_COMMIT = "abd2195ef6d79f609dd261b5e9c5402599625a64"
RUNTIME_STATUS_PATH = r"D:\NEXUS_RUNTIME\v13_b_reflection_completion_status.json"

# Canonical incomplete SoT (verified against real checkpoint counters when readable).
# Trust checkpoint over summaries; never claim V2.3 complete from these counts.
SOT_GROQ_SUCCESS = 53
SOT_GROQ_PENDING = 27
SOT_SAMBANOVA_SUCCESS = 16
SOT_SAMBANOVA_PENDING = 10
SOT_CASE_COUNT = 80
SOT_TERMINAL_STATUS = "INCOMPLETE_PROVIDER_CAPACITY"
SOT_V2_3_COMPLETE = False
SOT_GROQ_TARGET = 80

PROVIDER_LANES: tuple[str, ...] = (
    GROQ_REFLECTION_REASONER,
    SAMBANOVA_INDEPENDENT_CRITIC,
)

REAL_RESUME_OWNER = "local_Coordinator"
OPS_ROLE = "observability_and_manual_control_only_sanitized_fixtures"

HARD_BANS: tuple[str, ...] = (
    "no_real_provider_resume_ownership_theft",
    "no_secret_logging",
    "no_policy_effect_lessons_while_incomplete",
    "no_quality_eval_before_complete_denominators",
    "no_demo_exchange",
    "no_pr27_merge",
    "no_v2_3_complete_claim",
    "no_exchange_writes",
    "no_mainnet_real_money",
    "background_agent_sanitized_fixtures_only",
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
    "backend/nexus_v23_completion_ops",
    "tools/research/run_v23_completion_ops_v13.py",
    "tests/test_v23_completion_ops_v13.py",
    ARTIFACT_REL,
)

PROHIBITED_PATHS_UNTOUCHED: tuple[str, ...] = (
    "frontend",
    "backend/nexus_demo_execution",
    "backend/api",
    "pr27_merge_surfaces",
    "other_v13_lane_owned_paths",
)

BUCKET_PARAMS = DEFAULT_BUCKET_PARAMS

# Optional read-only counter verification path (never dump full checkpoint).
CANONICAL_CHECKPOINT_PATH = r"D:\NEXUS\btc_bot\.nexus_runtime\blind_reflection_v23_checkpoint.json"
