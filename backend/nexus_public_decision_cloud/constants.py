"""Public Decision Cloud (PUB-B) — constants and hard bans.

Local/staging read-only Decision Integrity surface. Never trades, never calls
exchange APIs, never imports Founder Private Core execution/research engines.
"""
from __future__ import annotations

SCHEMA_VERSION = "public_decision_cloud_v1"
PACKAGE = "backend.nexus_public_decision_cloud"
LANE = "PUB-B"
LANE_NAME = "PUBLIC_DECISION_CLOUD_SERVICE"
BRANCH = "feature/public-v1-decision-cloud-service"
BASE_COMMIT = "39e6b1ae1a40698d02c4cb8de4d80fc412309cfc"
ARTIFACT_REL = "artifacts/public/decision_cloud"  # docs only; no *_status.json

# Freshness (seconds) — advisory for staging fixtures
FRESHNESS_FRESH_SECONDS = 300.0
FRESHNESS_STALE_SECONDS = 1800.0

HARD_BANS: tuple[str, ...] = (
    "no_customer_trading",
    "no_exchange_apis",
    "no_private_core_direct_imports",
    "no_order_placement",
    "no_execution_mutation",
    "no_account_secrets",
    "no_api_keys_in_payloads",
    "no_wallet_or_balance_exposure",
    "no_strategy_parameters_in_payloads",
    "no_private_lesson_memory",
    "no_strategy_weights",
    "no_exact_entry_exit_logic",
    "no_copy_trading",
    "no_automatic_orders",
    "read_only_only",
    "local_staging_fixture_market_only",
)

# Keys that must never appear in Decision Cloud payloads
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

# Modules this package must never import (private-core / trading / exchange)
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

# Exchange / trading network markers forbidden in owned source
EXCHANGE_API_MARKERS: tuple[str, ...] = (
    "api.bybit.com",
    "api-testnet.bybit.com",
    "api.binance.com",
    "testnet.binance.vision",
    "fapi.binance.com",
    "api.krx.com",
    "api.coinbase.com",
    "ccxt.",
    "urllib.request",  # Decision Cloud must not open network for markets
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_public_decision_cloud",
    "tools/public/run_decision_cloud_hard_ban_passes.py",
    "tests/test_public_decision_cloud_service.py",
)

PROHIBITED_PATHS_UNTOUCHED: tuple[str, ...] = (
    "backend/trading",
    "backend/fleets",
    "backend/wallet",
    "backend/nexus_demo_execution",
    "frontend",
)

# Surfaces exposed by the read-only service
SURFACES: tuple[str, ...] = (
    "market_overview",
    "decision_feed",
    "decision_detail",
    "evidence",
    "counter_evidence",
    "risk",
    "thesis_monitor",
    "decision_memory",
    "outcome_review",
    "alerts",
    "freshness",
)

ALLOWED_HTTP_METHODS: tuple[str, ...] = ("GET", "HEAD", "OPTIONS")
