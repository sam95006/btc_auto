"""V18-E AI Gateway and Tool Sandbox — constants and hard bans."""
from __future__ import annotations

SCHEMA = "FOUNDER_V18_E_AI_GATEWAY_AND_TOOL_SANDBOX"
LANE = "V18-E"
LANE_NAME = "AI_GATEWAY_AND_TOOL_SANDBOX"
BRANCH = "feature/v18-ai-gateway-tool-sandbox"
BASE_COMMIT = "324e52f0573d7e3ad32feb2968274a52b8d8da75"
CAMPAIGN_ID = "v18_e_ai_gateway"
RANDOM_SEED = 20260806
PROMPT_SCHEMA_VERSION = "v18_e_gateway_prompt_v1"

# Unified provider IDs (same typed contract for every adapter).
PROVIDER_IDS: tuple[str, ...] = (
    "LOCAL",
    "OPENAI_COMPATIBLE",
    "GROQ",
    "SAMBANOVA",
    "OTHER_APPROVED_PROVIDER",
    "DETERMINISTIC_FALLBACK",
)

# Routing roles.
ROUTE_ROLES: tuple[str, ...] = (
    "SIMPLE",
    "CANDIDATE_INTERPRETATION",
    "MAJOR_CONTRADICTION_CRITIC",
)

# Default role → preferred provider (fallback chain handled by gateway).
ROLE_PRIMARY_PROVIDER: dict[str, str] = {
    "SIMPLE": "DETERMINISTIC_FALLBACK",
    "CANDIDATE_INTERPRETATION": "GROQ",
    "MAJOR_CONTRADICTION_CRITIC": "SAMBANOVA",
}

# Low-cost / simple alternate chain (never loops).
SIMPLE_PROVIDER_CHAIN: tuple[str, ...] = (
    "DETERMINISTIC_FALLBACK",
    "LOCAL",
)

PRIMARY_PROVIDER_CHAIN: tuple[str, ...] = (
    "GROQ",
    "OPENAI_COMPATIBLE",
    "LOCAL",
    "DETERMINISTIC_FALLBACK",
)

CRITIC_PROVIDER_CHAIN: tuple[str, ...] = (
    "SAMBANOVA",
    "OTHER_APPROVED_PROVIDER",
    "DETERMINISTIC_FALLBACK",
)

ROLE_PROVIDER_CHAIN: dict[str, tuple[str, ...]] = {
    "SIMPLE": SIMPLE_PROVIDER_CHAIN,
    "CANDIDATE_INTERPRETATION": PRIMARY_PROVIDER_CHAIN,
    "MAJOR_CONTRADICTION_CRITIC": CRITIC_PROVIDER_CHAIN,
}

# Result statuses (gateway-level).
RESULT_STATUSES: tuple[str, ...] = (
    "SUCCESS",
    "INVALID_SCHEMA",
    "TIMEOUT",
    "RATE_LIMITED",
    "PROVIDER_UNAVAILABLE",
    "BUDGET_EXCEEDED",
    "TOOL_DENIED",
    "CACHE_HIT",
    "DEDUPE_HIT",
    "PROVIDER_CAPACITY_BLOCKED",
    "UNKNOWN",
)

# Pipeline / decision when AI capacity is exhausted — never freeze, never busy-loop.
CAPACITY_STATUS = "PROVIDER_CAPACITY_BLOCKED"
PIPELINE_CONTINUE = "CONTINUE_WITHOUT_AI"
CAPACITY_DECISIONS: tuple[str, ...] = ("WAIT", "ABSTAIN")

DECISIONS: tuple[str, ...] = (
    "LONG",
    "SHORT",
    "WAIT",
    "REDUCE",
    "ABSTAIN",
    "BLOCK",
)

# Read-only tools AI may call.
ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "market_snapshot",
        "candidate",
        "evidence",
        "counter_evidence",
        "regime",
        "data_trust",
        "decision_memory",
        "public_news_context",
        "historical_similar_cases",
        "capture_health",
    }
)

# Explicitly banned tool classes.
BANNED_TOOLS: frozenset[str] = frozenset(
    {
        "exchange_write",
        "account_access",
        "wallet_access",
        "api_secret_access",
        "risk_override",
        "leverage_override",
        "lesson_activation",
        "strategy_deployment",
        "code_deployment",
    }
)

# Alias map for founder phrasing → canonical tool id.
TOOL_ALIASES: dict[str, str] = {
    "market snapshot": "market_snapshot",
    "counter-evidence": "counter_evidence",
    "counter evidence": "counter_evidence",
    "Data Trust": "data_trust",
    "data trust": "data_trust",
    "Decision Memory": "decision_memory",
    "decision memory": "decision_memory",
    "public news context": "public_news_context",
    "historical similar cases": "historical_similar_cases",
    "capture health": "capture_health",
    "exchange write": "exchange_write",
    "account access": "account_access",
    "wallet access": "wallet_access",
    "API secret access": "api_secret_access",
    "api secret access": "api_secret_access",
    "risk override": "risk_override",
    "leverage override": "leverage_override",
    "Lesson activation": "lesson_activation",
    "lesson activation": "lesson_activation",
    "strategy deployment": "strategy_deployment",
    "code deployment": "code_deployment",
}

DEFAULT_TIMEOUT_S = 8.0
DEFAULT_BUDGET_TOKENS = 8_000
DEFAULT_BUDGET_CALLS = 32
DEFAULT_CACHE_TTL_S = 60.0
MAX_PROVIDER_ATTEMPTS_PER_REQUEST = 4  # hard cap — prevents busy-loop

HARD_BANS: frozenset[str] = frozenset(
    {
        "no_busy_loop",
        "no_exchange_write",
        "no_account_wallet_access",
        "no_api_secret_access",
        "no_risk_override",
        "no_leverage_override",
        "no_lesson_activation",
        "no_strategy_deployment",
        "no_code_deployment",
        "no_freeze_pipeline_on_provider_outage",
        "no_mainnet",
        "no_real_money",
        "no_pr26_merge",
        "no_pr27_merge",
        "no_acceleration_report_edit",
        "no_status_json_artifact",
        "on_demand_zero",
    }
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_ai_gateway_tool_sandbox",
    "tools/research/ai_gateway_tool_sandbox",
    "tests/ai_gateway_tool_sandbox",
)

FORBIDDEN_ARTIFACT_SUFFIXES: tuple[str, ...] = (
    "_status.json",
    "_report.json",
    "_lane_status.json",
)
