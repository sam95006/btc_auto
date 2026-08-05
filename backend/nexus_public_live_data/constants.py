"""Public Live Data Adapter (PUB-C) — constants and hard bans.

Binds public-safe fields to real system sources with full lineage.
Never fabricates live values. Fixture mode is explicitly DEMO_DATA.
"""
from __future__ import annotations

SCHEMA_VERSION = "public_live_data_adapter_v1"
PACKAGE = "backend.nexus_public_live_data"
LANE = "PUB-C"
LANE_NAME = "LIVE_DATA_ADAPTER_AND_LINEAGE"
BRANCH = "feature/public-v1-live-data-adapter"
BASE_COMMIT = "39e6b1ae1a40698d02c4cb8de4d80fc412309cfc"

# Modes
MODE_LIVE = "LIVE"
MODE_FIXTURE = "FIXTURE"
DEMO_DATA_BANNER = "DEMO_DATA"

# Freshness / availability vocabulary (directive)
STATE_LIVE = "LIVE"
STATE_FRESH = "FRESH"
STATE_STALE = "STALE"
STATE_DEGRADED = "DEGRADED"
STATE_UNAVAILABLE = "UNAVAILABLE"
STATE_BLOCKED = "BLOCKED"
STATE_DEMO = "DEMO_DATA"

FRESHNESS_STATES: tuple[str, ...] = (
    STATE_LIVE,
    STATE_FRESH,
    STATE_STALE,
    STATE_DEGRADED,
    STATE_UNAVAILABLE,
    STATE_BLOCKED,
    STATE_DEMO,
)

COMPLETENESS_COMPLETE = "COMPLETE"
COMPLETENESS_PARTIAL = "PARTIAL"
COMPLETENESS_MISSING = "MISSING"
COMPLETENESS_BLOCKED = "BLOCKED"
COMPLETENESS_DEMO = "DEMO_DATA"

# Advisory age bands (seconds) for live public-safe reads
FRESH_SECONDS = 15.0
STALE_SECONDS = 120.0
DEGRADED_SECONDS = 600.0

HARD_BANS: tuple[str, ...] = (
    "no_fabricated_live_values",
    "no_silent_fixture_fallback_in_live_mode",
    "no_synthetic_fill_of_missing_live_data",
    "no_customer_trading",
    "no_exchange_write",
    "no_demo_orders",
    "no_shadow_orders",
    "no_mainnet_trading",
    "no_real_money",
    "no_copy_trading",
    "no_automatic_customer_orders",
    "no_private_core_execution_imports",
    "no_private_lesson_memory",
    "no_strategy_parameters_in_payloads",
    "no_account_secrets",
    "no_wallet_or_balance_exposure",
    "no_api_keys_in_payloads",
    "fixture_mode_must_show_DEMO_DATA",
    "local_staging_only",
)

FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "password",
        "private_key",
        "authorization",
        "strategy_parameters",
        "strategy_weights",
        "account_balance",
        "wallet_address",
        "bybit_api_key",
        "bybit_api_secret",
        "binance_api_key",
        "binance_api_secret",
        "lesson_memory_private",
        "founder_fill",
        "order_id",
        "client_order_id",
        "exchange_order_id",
    }
)

# Private-core / trading packages this adapter must never import
PRIVATE_CORE_IMPORT_PREFIXES: tuple[str, ...] = (
    "backend.trading",
    "backend.fleets",
    "backend.wallet",
    "backend.nexus_demo_execution",
    "backend.nexus_autonomy",
    "backend.nexus_execution",
    "backend.nexus_research_validation",
    "backend.governance",
    "backend.portfolio",
    "backend.risk.risk_control_engine",
    "backend.risk.dynamic_leverage_engine",
)

# Markers that imply write / trading capability (banned in owned source)
EXCHANGE_WRITE_MARKERS: tuple[str, ...] = (
    "EXCHANGE_WRITE=True",
    "MAINNET=True",
    "REAL_MONEY=True",
    "place_order",
    "submit_order",
    "create_order",
    "execute_trade",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_public_live_data",
    "tools/public/run_live_data_hard_ban_passes.py",
    "tests/test_public_live_data_adapter.py",
)

PROHIBITED_PATHS_UNTOUCHED: tuple[str, ...] = (
    "backend/trading",
    "backend/fleets",
    "backend/wallet",
    "backend/nexus_demo_execution",
)

# Public-safe field IDs bound by this adapter
PUBLIC_SAFE_FIELDS: tuple[str, ...] = (
    "market.last_price.BTCUSDT",
    "market.last_price.ETHUSDT",
    "market.last_price.SOLUSDT",
    "market.mark_price.BTCUSDT",
    "market.funding_rate.BTCUSDT",
    "system.runtime_health",
    "system.capture_campaign_health",
    "system.reflection_v23_progress",
    "system.qualification_state",
    "system.event_study_readiness",
    "system.qualification_ready_count",
    "decision.cloud.freshness",
    "decision.cloud.availability",
)

LINEAGE_REQUIRED_KEYS: tuple[str, ...] = (
    "source_system",
    "source_endpoint",
    "source_field",
    "as_of",
    "retrieved_at",
    "freshness",
    "completeness",
    "lineage_id",
    "fallback",
)

ALLOWED_HTTP_METHODS: tuple[str, ...] = ("GET", "HEAD", "OPTIONS")

# Public read-only market source (LIVE mode only; never writes)
BYBIT_PUBLIC_REST = "https://api.bybit.com"
BYBIT_TICKERS_PATH = "/v5/market/tickers"
BYBIT_CATEGORY = "linear"
ALLOWED_SYMBOLS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
