"""PUB18 Alert Engine — shared read-only contract constants (web + mobile).

Contract-only surface. Emits honesty metadata; never execution controls.
"""
from __future__ import annotations

SCHEMA = "pub18_alert_engine_readonly_contract_v1"
SCHEMA_VERSION = "1"
PACKAGE = "backend.nexus_pub18_alert_engine"
PROGRAM_ID = "NEXUS_PUB18_ALERT_ENGINE_READONLY"
BRANCH = "feature/nexus-public-v18-live-shadow-candidate"
BASE_COMMIT = "058c3e120e0709d7ff53e8338e431278fbbd093a"

# Canonical alert kinds (shared web/mobile). Order is founder-facing catalog order.
ALERT_KINDS: tuple[str, ...] = (
    "OPPORTUNITY_READY",
    "POSTURE_CHANGE",
    "DATA_TRUST_DEGRADED",
    "REGIME_TRANSITION",
    "INVALIDATION",
    "SHADOW_CLOSED",
    "PROVIDER_DEGRADED",
    "MARKET_ANOMALY",
    "MAJOR_RISK",
)

ALERT_KIND_LABELS: dict[str, str] = {
    "OPPORTUNITY_READY": "Opportunity READY",
    "POSTURE_CHANGE": "Posture change",
    "DATA_TRUST_DEGRADED": "Data Trust degraded",
    "REGIME_TRANSITION": "Regime transition",
    "INVALIDATION": "Invalidation",
    "SHADOW_CLOSED": "Shadow closed",
    "PROVIDER_DEGRADED": "Provider degraded",
    "MARKET_ANOMALY": "Market anomaly",
    "MAJOR_RISK": "Major risk",
}

# Required envelope fields on every public alert (read-only).
REQUIRED_FIELDS: tuple[str, ...] = (
    "kind",
    "source",
    "as_of",
    "freshness",
    "data_class",
    "decision_id",
    "reason",
    "severity",
    "public_safe",
)

SEVERITIES: tuple[str, ...] = ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL")

FRESHNESS_STATES: tuple[str, ...] = (
    "FRESH",
    "STALE",
    "DEGRADED",
    "UNAVAILABLE",
    "DEMO_DATA",
    "FIXTURE",
)

DATA_CLASS_LABELS: tuple[str, ...] = (
    "LIVE_READ_ONLY",
    "STALE",
    "UNAVAILABLE",
    "FIXTURE",
    "DEMO_DATA",
    "PROVIDER_REQUIRED",
)

# Member-facing text must never claim execution or guaranteed outcomes.
HYPE_PHRASES: tuple[str, ...] = (
    "already ordered",
    "order already filled",
    "filled for you",
    "guaranteed profit",
    "guaranteed return",
    "guaranteed wins",
    "risk-free",
    "risk free",
    "sure win",
    "sure profit",
    "must buy",
    "must sell",
    "buy now",
    "sell now",
    "trade now",
    "copy trade now",
    "auto-execute",
    "auto execute",
    "locked in profit",
    "profit locked",
    "you are in profit",
    "position opened",
    "order placed",
)

HARD_BANS: tuple[str, ...] = (
    "read_only_alerts_only",
    "no_hype_phrases",
    "no_fabricated_live_alerts",
    "no_unavailable_as_zero",
    "no_stale_without_indicator",
    "no_execution_controls",
    "no_member_exchange_write",
    "no_customer_trading",
    "no_trade_buttons",
    "no_private_core_imports",
    "no_private_field_leak",
    "public_safe_must_be_true",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_acceleration_report_edit",
    "no_archive_rebuild",
)

FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "position_size",
        "position_qty",
        "leverage",
        "exact_entry",
        "exact_stop",
        "entry_price",
        "order_id",
        "client_order_id",
        "exchange_order_id",
        "place_order",
        "submit_order",
        "create_order",
        "execute_trade",
        "trade_now",
        "api_key",
        "api_secret",
        "wallet_address",
        "account_balance",
        "strategy_weights",
        "private_threshold",
        "lesson_memory",
        "private_prompt",
        "founder_authorization",
    }
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
    "backend.nexus_learning",
    "backend.risk",
    "ccxt",
    "pybit",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_pub18_alert_engine",
    "frontend/src/member/alerts",
    "mobile/nexus_notify_prototypes/lib/src/pub18_alert_engine.dart",
    "tests/pub18_alert_engine",
    "tools/public/run_pub18_alert_engine_gate.py",
)

PASS_RECOMMENDATION = "NEXUS_PUB18_ALERT_ENGINE_READONLY_PASS"
FAIL_RECOMMENDATION = "NEXUS_PUB18_ALERT_ENGINE_READONLY_FAIL"

ARTIFACT_REL = "artifacts/readiness/immutable/pub18_alert_engine"
CONTRACT_REL = f"{ARTIFACT_REL}/alert_engine_readonly_contract.json"
