"""PUB-F Real-Time Transport — constants and hard bans.

LOCAL/STAGING public-safe streaming for Decision Integrity events.
Never exposes private Founder event streams, never trades, never
imports Private Core execution/research engines.
"""
from __future__ import annotations

SCHEMA_VERSION = "public_realtime_transport_v1"
PACKAGE = "backend.nexus_public_realtime_transport"
LANE = "PUB-F"
LANE_NAME = "PUBLIC_REALTIME_TRANSPORT"
BRANCH = "feature/public-v1-realtime-transport"
BASE_COMMIT = "39e6b1ae1a40698d02c4cb8de4d80fc412309cfc"
ARTIFACT_REL = "artifacts/public/realtime_transport"  # no *_status.json

DEPLOYMENT_ENVIRONMENTS: frozenset[str] = frozenset({"LOCAL", "STAGING"})
FORBIDDEN_ENVIRONMENTS: frozenset[str] = frozenset({"PRODUCTION", "PROD", "MAINNET"})

# Transport timing (seconds)
HEARTBEAT_INTERVAL_SECONDS = 15.0
STALE_AFTER_SECONDS = 45.0
POLL_INTERVAL_SECONDS = 5.0
RESUME_TOKEN_TTL_SECONDS = 3600.0
SEQUENCE_BUFFER_CAPACITY = 512

# Reconnect / backoff (client protocol helpers)
BACKOFF_INITIAL_SECONDS = 0.5
BACKOFF_MAX_SECONDS = 30.0
BACKOFF_MULTIPLIER = 2.0
BACKOFF_JITTER_RATIO = 0.2

# Public-safe event kinds only
ALLOWED_EVENT_KINDS: frozenset[str] = frozenset(
    {
        "heartbeat",
        "resume_ack",
        "staleness",
        "availability",
        "decision_update",
        "thesis_alert",
        "freshness_change",
        "outcome_review",
        "evidence_refresh",
        "stream_end",
        "gap_notice",
    }
)

# Topics that must never be subscribed or published on this transport
FORBIDDEN_PRIVATE_TOPICS: frozenset[str] = frozenset(
    {
        "private.events",
        "private.event_stream",
        "founder.runtime",
        "founder.private",
        "lesson.memory",
        "lesson_memory",
        "execution.orders",
        "execution.fills",
        "execution.positions",
        "wallet.balances",
        "risk.governor",
        "strategy.signals",
        "strategy.weights",
        "fleet.commands",
        "autonomy.loop",
        "exchange.user_stream",
        "binance.user_stream",
        "bybit.private",
    }
)

HARD_BANS: tuple[str, ...] = (
    "no_private_event_stream_exposure",
    "no_live_public_deployment",
    "no_app_store_submission",
    "no_google_play_submission",
    "no_live_billing",
    "no_real_iap_products",
    "no_production_customer_database",
    "no_custodial_wallet",
    "no_copy_trading",
    "no_automated_customer_trading",
    "no_customer_trading",
    "no_exchange_write",
    "no_demo_order",
    "no_shadow_order",
    "no_mainnet",
    "no_real_money",
    "no_PR26_merge",
    "no_PR27_merge",
    "no_private_core_direct_imports",
    "no_order_placement",
    "no_account_secrets",
    "no_strategy_parameters_in_payloads",
    "no_private_lesson_memory",
    "no_fabricated_edge",
    "no_auto_integrate",
)

FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "password",
        "private_key",
        "authorization",
        "strategy_parameters",
        "strategy_weights",
        "strategy_id",
        "account_balance",
        "wallet_address",
        "lesson_memory",
        "lesson_memory_private",
        "founder_fill",
        "order_id",
        "client_order_id",
        "exchange_order_id",
        "position_id",
        "fill",
        "fills",
        "leverage",
        "margin",
        "raw_provider_prompt",
        "system_prompt",
        "private_risk",
        "execution_route",
    }
)

PRIVATE_CORE_IMPORT_PREFIXES: tuple[str, ...] = (
    "backend.trading",
    "backend.fleets",
    "backend.wallet",
    "backend.portfolio",
    "backend.learning",
    "backend.nexus_demo_execution",
    "backend.nexus_autonomy",
    "backend.nexus_execution",
    "backend.nexus_research",
    "backend.nexus_research_validation",
    "backend.governance",
    "backend.risk.risk_control_engine",
    "backend.risk.dynamic_leverage_engine",
    "ccxt",
    "pybit",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_public_realtime_transport/",
    "tools/public/run_realtime_transport_hard_ban_passes.py",
    "tests/test_public_realtime_transport.py",
    "artifacts/public/realtime_transport/",
)

PROHIBITED_PATHS_UNTOUCHED: tuple[str, ...] = (
    "backend/trading",
    "backend/fleets",
    "backend/wallet",
    "backend/nexus_demo_execution",
    "frontend",
)

TRANSPORT_MODES: tuple[str, ...] = ("sse", "websocket", "polling")
