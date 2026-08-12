"""V16-H Decision Memory Graph — constants and hard bans."""
from __future__ import annotations

SCHEMA_ID = "FOUNDER_V16_H_DECISION_MEMORY_GRAPH"
SCHEMA_VERSION = 1
GRAPH_SCHEMA = "nexus_decision_memory_graph_v16_h"
NODE_SCHEMA = "nexus_decision_memory_node_v16_h"
EDGE_SCHEMA = "nexus_decision_memory_edge_v16_h"
SIMILARITY_CONTRACT = "nexus_decision_memory_similarity_v16_h"
PUBLIC_PROJECTION_SCHEMA = "nexus_decision_memory_public_projection_v16_h"

LANE = "V16-H"
LANE_NAME = "DECISION_MEMORY_GRAPH"
BRANCH = "feature/v16-decision-memory-graph"
BASE_COMMIT = "f01407e5d7c7e4c00e0eb1616dc5ef74d91a58b5"

# Canonical node kinds linked by the Market Decision Memory Graph.
NODE_KINDS: tuple[str, ...] = (
    "MARKET_SNAPSHOT",
    "SYMBOL",
    "REGIME",
    "CANDIDATE",
    "STRATEGY_EXPERT",
    "REASONER",
    "CRITIC",
    "SUPPORTING_EVIDENCE",
    "CONTRADICTING_EVIDENCE",
    "RISK_DECISION",
    "ENTRY",
    "EXIT",
    "COSTS",
    "OUTCOME",
    "ERROR_CLASSIFICATION",
    "REFLECTION",
    "LESSON",
    "COUNTERFACTUAL",
    "VALIDATION",
    "CODE_VERSION",
    "MODEL_VERSION",
    "POLICY_VERSION",
    "DECISION",
)

# Directed edge kinds (from -> to).
EDGE_KINDS: tuple[str, ...] = (
    "OBSERVES",
    "OF_SYMBOL",
    "IN_REGIME",
    "PROPOSED_BY",
    "ROUTED_TO_EXPERT",
    "REASONED_BY",
    "CRITICIZED_BY",
    "SUPPORTED_BY",
    "CONTRADICTED_BY",
    "RISK_VERDICT",
    "ENTERED_VIA",
    "EXITED_VIA",
    "INCURRED_COST",
    "RESULTED_IN",
    "CLASSIFIED_AS",
    "REFLECTED_IN",
    "PRODUCED_LESSON",
    "COUNTERFACTUAL_OF",
    "VALIDATED_BY",
    "PINNED_CODE",
    "PINNED_MODEL",
    "PINNED_POLICY",
    "PART_OF_DECISION",
)

# Fields never projected to public surfaces.
PRIVATE_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "api_key",
        "api_secret",
        "token",
        "password",
        "private_key",
        "secret",
        "authorization",
        "exchange_credentials",
        "wallet_seed",
        "internal_strategy_source",
        "proprietary_threshold",
        "exact_risk_threshold",
        "leverage_override",
        "raw_memory_blob",
        "private_execution_control",
        "founder_only_note",
        "provider_raw_response",
        "account_id",
        "wallet_address",
    }
)

# Public-safe node payload keys (whitelist for public projection).
PUBLIC_SAFE_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "symbol",
        "label",
        "summary",
        "status",
        "regime_label",
        "expert_label",
        "side",
        "recommendation",
        "abstention_reason",
        "uncertainty",
        "freshness",
        "evidence_count",
        "supporting_count",
        "contradicting_count",
        "outcome_class",
        "error_class",
        "lesson_label",
        "validation_status",
        "version_label",
        "similarity_tags",
        "as_of_ms",
        "pit_bound",
        "data_class",
    }
)

FORBIDDEN_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "token",
        "password",
        "private_key",
        "authorization",
        "access_token",
        "refresh_token",
        "client_secret",
        "wallet_seed",
        "mnemonic",
        "exchange_credentials",
    }
)

HARD_BANS: tuple[str, ...] = (
    "no_pr26_merge",
    "no_pr27_merge",
    "no_demo_orders",
    "no_shadow_orders",
    "no_exchange_writes",
    "no_mainnet",
    "no_real_money",
    "no_secret_storage",
    "no_private_field_leak_to_public",
    "no_required_external_graph_db",
    "no_status_json_lane_reports",
    "no_fabricated_ai_learning",
    "no_profitability_claims",
    "no_auto_integrate",
    "no_rewrite_real_ledger",
    "no_future_leakage_in_pit",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_decision_memory_graph",
    "tests/decision_memory_graph",
)

EVIDENCE_CLASS = "FIXTURE_AND_DEVELOPMENT_ONLY"
UNAVAILABLE_MODE = "GRAPH_UNAVAILABLE_FAIL_SAFE"
DEFAULT_CODE_VERSION = "v16_h_decision_memory_graph_1"
DEFAULT_MODEL_VERSION = "fixture_model_none"
DEFAULT_POLICY_VERSION = "deterministic_policy_v1"
