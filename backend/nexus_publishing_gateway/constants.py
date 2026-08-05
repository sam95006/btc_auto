"""PUB-A Intelligence Publishing Gateway — constants and hard bans."""
from __future__ import annotations

SCHEMA = "public.intelligence.v1"
PROGRAM_ID = "NEXUS_PUBLIC_V1_INTELLIGENCE_PUBLISHING_GATEWAY"
LANE = "PUB-A"
BRANCH = "feature/public-v1-intelligence-publishing-gateway"
BASE_HEAD = "39e6b1ae1a40698d02c4cb8de4d80fc412309cfc"

DEPLOYMENT_ENVIRONMENTS: frozenset[str] = frozenset({"LOCAL", "STAGING"})
FORBIDDEN_ENVIRONMENTS: frozenset[str] = frozenset({"PRODUCTION", "PROD", "MAINNET"})

# Public DTO allow-list (top-level + nested public field names).
ALLOWED_PUBLIC_FIELDS: frozenset[str] = frozenset(
    {
        # envelope
        "schema_version",
        "published_at",
        "availability",
        "environment",
        "lineage_id",
        "payload",
        # market
        "market_state",
        "market_timestamp",
        "data_freshness",
        "data_completeness",
        "symbol",
        "symbols",
        "regime_label",
        # evidence
        "evidence_summary",
        "evidence_summaries",
        "contradicting_evidence",
        "evidence_polarity",
        "evidence_freshness",
        "source_label",
        "citation_count",
        # risk (public alerts only)
        "risk_alerts",
        "risk_alert",
        "alert_severity",
        "alert_code",
        "alert_message",
        # thesis / confidence / decision / outcome
        "thesis_status",
        "thesis_horizon",
        "confidence_calibration",
        "confidence_band",
        "decision_state",
        "decision_posture",
        "outcome_review_classification",
        "outcome_status",
        # system
        "system_availability",
        "freshness_state",
        "completeness_state",
        "as_of",
        "retrieved_at",
        "status",
        "message",
        "count",
        "bucket",
    }
)

# Explicit deny traps — presence anywhere blocks publish (fail-closed).
DENIED_PRIVATE_FIELDS: frozenset[str] = frozenset(
    {
        "strategy_id",
        "strategy_ids",
        "strategy_parameters",
        "strategy_params",
        "strategy_weights",
        "entry_threshold",
        "exit_threshold",
        "lesson_id",
        "lesson_ids",
        "private_lesson_id",
        "lesson_memory",
        "raw_provider_prompt",
        "raw_provider_response",
        "prompt",
        "prompts",
        "system_prompt",
        "order",
        "orders",
        "order_id",
        "order_ids",
        "order_link_id",
        "position",
        "positions",
        "position_id",
        "wallet",
        "wallets",
        "wallet_address",
        "wallet_data",
        "account",
        "accounts",
        "account_id",
        "account_data",
        "api_key",
        "api_secret",
        "api_passphrase",
        "provider_secret",
        "provider_secrets",
        "secret",
        "secrets",
        "private_key",
        "execution_route",
        "execution_routes",
        "route",
        "routes",
        "routing_table",
        "private_risk",
        "private_risk_internals",
        "risk_governor_state",
        "risk_internals",
        "fill",
        "fills",
        "leverage",
        "margin",
        "uid",
        "member_id",
    }
)

# Aggregation / k-anonymity style thresholds (LOCAL/STAGING defaults).
AGGREGATION_MIN_COUNT = 5
CONFIDENCE_BUCKETS: tuple[str, ...] = ("LOW", "MEDIUM", "HIGH", "UNAVAILABLE")
TIMING_PAD_MS = 25  # minimum response floor to reduce timing oracle

HARD_BANS: tuple[str, ...] = (
    "no_PR26_merge",
    "no_PR27_merge",
    "no_live_billing",
    "no_exchange_write",
    "no_production_deploy",
    "no_private_core_trading_imports",
    "no_mainnet",
    "no_real_money",
)

# Modules the gateway package must NEVER import (AST-enforced).
FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
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
    "backend.nexus_learning",
    "backend.risk",
    "ccxt",
    "pybit",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_publishing_gateway/",
    "tests/publishing_gateway/",
)

PASS_RECOMMENDATION = "NEXUS_PUBLIC_V1_INTELLIGENCE_PUBLISHING_GATEWAY_PASS"
FAIL_RECOMMENDATION = "NEXUS_PUBLIC_V1_INTELLIGENCE_PUBLISHING_GATEWAY_FAIL"
