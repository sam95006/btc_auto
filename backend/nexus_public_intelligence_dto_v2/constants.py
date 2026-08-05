"""UX-A Public Intelligence DTO V2 — constants, allow-list, and hard bans.

Public-safe surface only. Never imports Founder Private Core.
"""
from __future__ import annotations

SCHEMA = "public.intelligence.v2"
SCHEMA_VERSION = "public.intelligence.v2"
PACKAGE = "backend.nexus_public_intelligence_dto_v2"
LANE = "UX-A"
LANE_NAME = "PUBLIC_INTELLIGENCE_DTO_V2"
BRANCH = "feature/v16-public-intelligence-dto-v2"
BASE_COMMIT = "cbad07e94e40e60c4b144fe63b22f40d26d8cf95"
PROGRAM_ID = "NEXUS_PUBLIC_INTELLIGENCE_DTO_V2"
PASS_COUNT = 3

# Public-safe AI recommendation states (no execution controls).
AI_RECOMMENDATION_STATES: frozenset[str] = frozenset(
    {
        "RECOMMEND",
        "HOLD",
        "WAIT",
        "ABSTAIN",
        "UNAVAILABLE",
    }
)

# Public decision lifecycle statuses (customer-readable; no private execution stages).
DECISION_LIFECYCLE_STATUSES: frozenset[str] = frozenset(
    {
        "OBSERVING",
        "EVIDENCE_REVIEW",
        "DECIDING",
        "MONITORING",
        "OUTCOME_REVIEW",
        "CLOSED",
        "ABSTAINED",
        "UNAVAILABLE",
    }
)

# Public strategy expert labels (display labels only — not internal strategy sources).
STRATEGY_EXPERT_LABELS: frozenset[str] = frozenset(
    {
        "TREND",
        "MEAN_REVERSION",
        "BREAKOUT",
        "LIQUIDATION",
        "EVENT",
        "DEFENSIVE_NO_TRADE",
        "UNASSIGNED",
        "UNAVAILABLE",
    }
)

# Public lesson-applied labels (never lesson_id / private memory).
LESSON_APPLIED_LABELS: frozenset[str] = frozenset(
    {
        "NONE",
        "LESSON_APPLIED",
        "LESSON_CANDIDATE",
        "LESSON_BLOCKED",
        "UNAVAILABLE",
    }
)

# Regime probability keys exposed publicly (descriptive PIT measurement only).
REGIME_PROBABILITY_KEYS: tuple[str, ...] = (
    "strong_bull_probability",
    "strong_bear_probability",
    "volatility_expansion_probability",
    "liquidity_stress_probability",
    "long_crowding_probability",
    "correlation_breakdown_probability",
    "event_risk_probability",
    "regime_transition_probability",
    "regime_confidence",
    "regime_freshness",
)

# Allow-listed public field names for the V2 intelligence DTO envelope + payload.
ALLOWED_PUBLIC_FIELDS: frozenset[str] = frozenset(
    {
        # envelope
        "schema_version",
        "published_at",
        "availability",
        "environment",
        "lineage_id",
        "payload",
        "data_class",
        "symbol",
        "decision_id",
        "as_of",
        "retrieved_at",
        # regime probabilities (public-safe)
        "regime_probabilities",
        "regime_label",
        "strong_bull_probability",
        "strong_bear_probability",
        "volatility_expansion_probability",
        "liquidity_stress_probability",
        "long_crowding_probability",
        "correlation_breakdown_probability",
        "event_risk_probability",
        "regime_transition_probability",
        "regime_confidence",
        "regime_freshness",
        # AI recommendation
        "ai_recommendation_state",
        "ai_recommendation_message",
        # evidence
        "supporting_evidence",
        "contradicting_evidence",
        "evidence_summary",
        "evidence_polarity",
        "evidence_freshness",
        "source_label",
        "citation_count",
        # uncertainty / abstention
        "uncertainty",
        "uncertainty_band",
        "abstention_reason",
        "abstention_code",
        # strategy / lesson labels (public only)
        "strategy_expert_label",
        "lesson_applied_label",
        # similar-case summary (never raw memory graph)
        "similar_case_summary",
        "similar_case_count",
        "similar_case_overlap_band",
        # freshness
        "data_freshness",
        "freshness_state",
        "stale_indicator",
        "unavailable_indicator",
        # lifecycle
        "decision_lifecycle_status",
        "decision_state",
        "decision_posture",
        "confidence_band",
        # system
        "system_availability",
        "status",
        "message",
        "count",
        "raw_memory_graph",
        "private_fields_included",
        "private_core_import_count",
    }
)

# Explicit deny traps — presence anywhere fails closed.
DENIED_PRIVATE_FIELDS: frozenset[str] = frozenset(
    {
        # secrets
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
        "exchange_credentials",
        "kill_switch_token",
        # internal strategy source
        "strategy_id",
        "strategy_ids",
        "strategy_source",
        "internal_strategy_source",
        "strategy_parameters",
        "strategy_params",
        "strategy_weights",
        "expert_weights",
        "routing_table",
        # private execution controls
        "execution_route",
        "execution_routes",
        "execution_controls",
        "order",
        "orders",
        "order_id",
        "order_ids",
        "order_link_id",
        "client_order_id",
        "exchange_order_id",
        "position",
        "positions",
        "position_id",
        "place_order",
        "submit_order",
        "leverage",
        "margin",
        "fill",
        "fills",
        # proprietary thresholds
        "entry_threshold",
        "exit_threshold",
        "proprietary_threshold",
        "proprietary_thresholds",
        "threshold_table",
        "risk_governor_state",
        "private_risk",
        "private_risk_internals",
        "risk_internals",
        # raw private memory graph
        "raw_memory_blob",
        "memory_graph_raw",
        "private_memory_graph",
        "lesson_memory",
        "lesson_id",
        "lesson_ids",
        "private_lesson_id",
        "graph_nodes_raw",
        "graph_edges_raw",
        # prompts / provider internals
        "raw_provider_prompt",
        "raw_provider_response",
        "prompt",
        "prompts",
        "system_prompt",
        # identity / wallet
        "wallet",
        "wallets",
        "wallet_address",
        "wallet_data",
        "account",
        "accounts",
        "account_id",
        "account_data",
        "uid",
        "member_id",
    }
)

HARD_BANS: tuple[str, ...] = (
    "no_secrets",
    "no_internal_strategy_source",
    "no_private_execution_controls",
    "no_proprietary_thresholds",
    "no_raw_private_memory_graph",
    "no_exchange_write",
    "no_private_core_imports",
    "no_PR26_merge",
    "no_PR27_merge",
    "no_production_deploy",
    "no_mainnet",
    "no_real_money",
    "no_demo_orders",
    "no_shadow_orders",
    "no_status_json_artifact",
    "no_acceleration_report_edit",
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
    "backend.nexus_probabilistic_regime_v2",
    "backend.nexus_uncertainty_abstention",
    "backend.nexus_private_control",
    "backend.nexus_private_core_redteam",
    "backend.governance",
    "backend.risk",
    "ccxt",
    "pybit",
)

EXCHANGE_WRITE_MARKERS: tuple[str, ...] = (
    "api.bybit.com",
    "api-testnet.bybit.com",
    "api.binance.com",
    "testnet.binance.vision",
    "fapi.binance.com",
    "api.okx.com",
    "api.coinbase.com",
    "ccxt.",
    "EXCHANGE_WRITE",
    "place_order",
    "submit_order",
    "create_order",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_public_intelligence_dto_v2/",
    "tests/public_intelligence_dto_v2/",
    "tools/public/run_public_intelligence_dto_v2_passes.py",
)

DEPLOYMENT_ENVIRONMENTS: frozenset[str] = frozenset({"LOCAL", "STAGING"})
FORBIDDEN_ENVIRONMENTS: frozenset[str] = frozenset({"PRODUCTION", "PROD", "MAINNET"})

PASS_RECOMMENDATION = "NEXUS_PUBLIC_INTELLIGENCE_DTO_V2_PASS"
FAIL_RECOMMENDATION = "NEXUS_PUBLIC_INTELLIGENCE_DTO_V2_FAIL"

UNCERTAINTY_BANDS: frozenset[str] = frozenset({"LOW", "MEDIUM", "HIGH", "UNAVAILABLE"})
FRESHNESS_STATES: frozenset[str] = frozenset({"FRESH", "STALE", "UNAVAILABLE"})
