"""PUB17-C Private-to-Public Projection V3 — constants, allow-list, hard bans."""
from __future__ import annotations

SCHEMA = "public.private_to_public_projection.v3"
SCHEMA_VERSION = "public.private_to_public_projection.v3"
PACKAGE = "backend.nexus_private_to_public_projection_v3"
LANE = "PUB17-C"
LANE_NAME = "PRIVATE_TO_PUBLIC_PROJECTION_V3"
BRANCH = "feature/pub17-private-to-public-projection-v3"
BASE_COMMIT = "8391c17e2d0d0ea9ee69c8e253cc5d71f1456da3"
PROGRAM_ID = "NEXUS_PRIVATE_TO_PUBLIC_PROJECTION_V3"

# Founder allow-list only (plus minimal envelope metadata).
ALLOWED_PUBLIC_FIELDS: frozenset[str] = frozenset(
    {
        # envelope
        "schema_version",
        "published_at",
        "symbol",
        "as_of",
        "retrieved_at",
        "availability",
        "environment",
        "lineage_id",
        "data_class",
        "payload",
        # allow-list intelligence surface
        "market_state",
        "regime_summary",
        "ai_public_suggestion",
        "risk_category",
        "evidence_summary",
        "counter_evidence_summary",
        "abstention_reason",
        "data_trust",
        "historical_similarity_aggregate",
        "delayed_aggregated_performance",
        # nested aggregate helpers (still public-safe)
        "overlap_band",
        "case_count_band",
        "performance_band",
        "window_label",
        "status",
        "message",
        "count",
        # attestation / fail-closed flags (must stay non-leaky)
        "member_execution_control_count",
        "private_fields_included",
        "raw_memory_graph",
        "private_core_import_count",
        "inference_survivors",
    }
)

# Explicit ban surface from Founder PUB17-C.
BANNED_PRIVATE_FIELDS: frozenset[str] = frozenset(
    {
        # private trade ledger
        "private_trade_ledger",
        "trade_ledger",
        "ledger_entry",
        "ledger_entries",
        "fills",
        "fill",
        # exchange credentials
        "exchange_credentials",
        "api_key",
        "api_secret",
        "api_passphrase",
        "provider_secret",
        "provider_secrets",
        "secret",
        "secrets",
        "private_key",
        "password",
        "authorization",
        "kill_switch_token",
        # exact strategy params / proprietary thresholds
        "strategy_parameters",
        "strategy_params",
        "strategy_weights",
        "exact_strategy_parameter",
        "exact_proprietary_threshold",
        "entry_threshold",
        "exit_threshold",
        "proprietary_threshold",
        "proprietary_thresholds",
        "threshold_table",
        "private_thresholds",
        "routing_table",
        "expert_weights",
        "strategy_id",
        "strategy_source",
        "internal_strategy_source",
        # Founder capital / exact private position
        "founder_capital",
        "capital",
        "wallet",
        "wallet_address",
        "account_balance",
        "exact_private_position",
        "position",
        "positions",
        "position_id",
        "position_size",
        "leverage",
        "margin",
        "entry_price",
        "exact_entry",
        "exact_stop",
        "order",
        "orders",
        "order_id",
        "client_order_id",
        "exchange_order_id",
        # private Lesson text
        "private_lesson_text",
        "lesson_text",
        "lesson_memory",
        "lesson_id",
        "lesson_ids",
        "private_lesson_id",
        # raw Decision Memory Graph nodes
        "raw_decision_memory_graph_nodes",
        "raw_memory_blob",
        "memory_graph_raw",
        "private_memory_graph",
        "graph_nodes_raw",
        "graph_edges_raw",
        "decision_memory_graph_nodes",
        # execution controls
        "execution_controls",
        "execution_control",
        "execution_route",
        "execution_routes",
        "place_order",
        "submit_order",
        "create_order",
        "copy_trade",
        "auto_trade",
        "member_execution_controls",
    }
)

AI_PUBLIC_SUGGESTIONS: frozenset[str] = frozenset(
    {"LONG", "SHORT", "WAIT", "ABSTAIN", "UNAVAILABLE"}
)

RISK_CATEGORIES: frozenset[str] = frozenset(
    {"LOW", "MEDIUM", "HIGH", "EXTREME", "UNAVAILABLE"}
)

DATA_TRUST_STATUSES: frozenset[str] = frozenset(
    {
        "TRUSTED",
        "USABLE_WITH_LIMITS",
        "DEGRADED",
        "STALE",
        "CONFLICTED",
        "LICENSE_BLOCKED",
        "UNAVAILABLE",
    }
)

PERFORMANCE_BANDS: frozenset[str] = frozenset(
    {"NEGATIVE", "FLAT", "POSITIVE", "UNAVAILABLE"}
)

CASE_COUNT_BANDS: frozenset[str] = frozenset(
    {"NONE", "LOW", "MEDIUM", "HIGH", "UNAVAILABLE"}
)

OVERLAP_BANDS: frozenset[str] = frozenset({"LOW", "MEDIUM", "HIGH", "UNAVAILABLE"})

# Coarse quantization for any numeric public signal (inference resistance).
QUANTIZATION_STEP = 0.1
# Hysteresis band so binary-search cannot pin exact private thresholds.
INFERENCE_HYSTERESIS = 0.05

HARD_BANS: tuple[str, ...] = (
    "allowlist_only_projection",
    "no_private_trade_ledger",
    "no_exchange_credentials",
    "no_exact_strategy_params",
    "no_exact_proprietary_thresholds",
    "no_founder_capital",
    "no_exact_private_position",
    "no_private_lesson_text",
    "no_raw_decision_memory_graph_nodes",
    "no_execution_controls",
    "member_execution_control_count_must_be_0",
    "inference_attack_survivors_must_be_0",
    "no_PR26_merge",
    "no_PR27_merge",
    "no_acceleration_report_edit",
    "no_production_deploy",
    "no_mainnet",
    "no_real_money",
)

PRIVATE_CORE_IMPORT_PREFIXES: tuple[str, ...] = (
    "backend.trading",
    "backend.wallet",
    "backend.portfolio",
    "backend.fleets",
    "backend.learning",
    "backend.nexus_research",
    "backend.nexus_demo_execution",
    "backend.nexus_autonomy",
    "backend.nexus_execution",
    "backend.nexus_strategy_engine",
    "backend.nexus_strategy_expert_router",
    "backend.nexus_learning",
    "backend.nexus_lesson_compiler",
    "backend.nexus_decision_memory_graph",
    "backend.nexus_private_control",
    "backend.nexus_private_core_redteam",
    "backend.governance",
    "backend.risk",
    "ccxt",
    "pybit",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_private_to_public_projection_v3/",
    "tests/private_to_public_projection_v3/",
)

PASS_RECOMMENDATION = "NEXUS_PRIVATE_TO_PUBLIC_PROJECTION_V3_PASS"
FAIL_RECOMMENDATION = "NEXUS_PRIVATE_TO_PUBLIC_PROJECTION_V3_FAIL"

DEPLOYMENT_ENVIRONMENTS: frozenset[str] = frozenset({"LOCAL", "STAGING"})
FORBIDDEN_ENVIRONMENTS: frozenset[str] = frozenset({"PRODUCTION", "PROD", "MAINNET"})

EXECUTION_CONTROL_KEYS: frozenset[str] = frozenset(
    {
        "execution_controls",
        "execution_control",
        "execution_route",
        "execution_routes",
        "place_order",
        "submit_order",
        "create_order",
        "copy_trade",
        "auto_trade",
        "member_execution_controls",
        "leverage_control",
        "position_control",
    }
)
