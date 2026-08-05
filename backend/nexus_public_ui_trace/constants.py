"""PUB-G UI data contract — constants and hard bans."""
from __future__ import annotations

SCHEMA = "public.intelligence.v1"
PROGRAM_ID = "NEXUS_PUBLIC_V1_UI_DATA_TRACEABILITY"
LANE = "PUB-G"
BRANCH = "feature/public-v1-ui-data-traceability"
BASE_HEAD = "39e6b1ae1a40698d02c4cb8de4d80fc412309cfc"

# Align with PUB-A allow-list (standalone copy; this branch does not import PUB-A).
ALLOWED_PUBLIC_FIELDS: frozenset[str] = frozenset(
    {
        # envelope / lineage
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
        # risk / alerts (public)
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
        "decision_title",
        "decision_id",
        "outcome_review_classification",
        "outcome_status",
        "review_note",
        # system / freshness
        "system_availability",
        "freshness_state",
        "completeness_state",
        "as_of",
        "retrieved_at",
        "status",
        "message",
        "count",
        "bucket",
        "stale_indicator",
        "unavailable_indicator",
        # member-surface public DTOs (non-intelligence)
        "tier_name",
        "tier_blurb",
        "entitlement_labels",
        "billing_note",
        "display_name",
        "email_masked",
        "locale",
        "timezone",
        "consent_marketing",
        "consent_analytics",
        "consent_crash",
        "notify_decision",
        "notify_risk",
        "notify_stale",
        "notify_thesis",
        "notify_anomaly",
        "deletion_requested",
        "export_requested",
        "nex_ai_availability",
        "nex_ai_disclaimer",
    }
)

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
        "exchange_credentials",
        "kill_switch_token",
        "qualification_internal",
    }
)

COMPONENT_KINDS: frozenset[str] = frozenset(
    {
        "card",
        "table",
        "chart",
        "gauge",
        "chip",
        "notification",
        "decision_summary",
    }
)

UI_MODES: frozenset[str] = frozenset({"LIVE", "DEMO", "MOCK"})

HARD_BANS: tuple[str, ...] = (
    "no_PR26_merge",
    "no_PR27_merge",
    "no_live_billing",
    "no_exchange_write",
    "no_production_deploy",
    "no_production_public_API",
    "no_private_core_trading_imports",
    "no_mainnet",
    "no_real_money",
    "no_status_json_artifacts",
)

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
    "backend/nexus_public_ui_trace/",
    "tools/public_v1/",
    "tests/public_ui_trace/",
    "frontend/src/public_ui_trace/",
    "docs/ui/NEXUS_PUBLIC_V1_UI_DATA_TRACEABILITY_V1.md",
)

REQUIRED_COUNTERS: tuple[str, ...] = (
    "visible_mock_value_count",
    "unmapped_live_component_count",
    "private_field_binding_count",
    "stale_without_indicator",
    "unavailable_fabrication",
)

PASS_RECOMMENDATION = "NEXUS_PUBLIC_V1_UI_DATA_TRACEABILITY_PASS"
FAIL_RECOMMENDATION = "NEXUS_PUBLIC_V1_UI_DATA_TRACEABILITY_FAIL"
