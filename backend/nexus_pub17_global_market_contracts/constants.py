"""PUB17-A — Global Market Source Contracts constants and hard bans."""
from __future__ import annotations

SCHEMA = "pub17_a_global_market_source_contracts_v1"
SCHEMA_VERSION = "1"
DTO_SCHEMA = "pub17_a_normalized_market_source_dto_v1"
PACKAGE = "backend.nexus_pub17_global_market_contracts"
LANE = "PUB17-A"
LANE_NAME = "GLOBAL_MARKET_SOURCE_CONTRACTS"
BRANCH = "feature/pub17-global-market-source-contracts"
BASE_COMMIT = "8391c17e2d0d0ea9ee69c8e253cc5d71f1456da3"
PROGRAM_ID = "NEXUS_PUB17_GLOBAL_MARKET_SOURCE_CONTRACTS"

ARTIFACT_REL = "artifacts/readiness/immutable/pub17_global_market_source_contracts"
SCHEMA_REL = f"{ARTIFACT_REL}/global_market_source_contracts.schema.json"
CATALOG_REL = f"{ARTIFACT_REL}/source_contracts_catalog.json"

# Domains required by founder directive (exact coverage set).
REQUIRED_DOMAINS: tuple[str, ...] = (
    "crypto",
    "us_equities",
    "asian_equities",
    "fx",
    "rates",
    "bonds",
    "commodities",
    "etf_flows",
    "macro_events",
    "regulatory_events",
    "security_incidents",
    "exchange_incidents",
    "ai_tech_sector",
)

# Contract / binding statuses. PROVIDER_REQUIRED = no legal source wired.
CONTRACT_STATUSES: tuple[str, ...] = (
    "CONTRACT_READY",
    "PROVIDER_REQUIRED",
    "LICENSE_REVIEW_REQUIRED",
)

# Freshness / availability vocabulary — never fabricate LIVE values.
FRESHNESS_STATES: tuple[str, ...] = (
    "LIVE",
    "FRESH",
    "STALE",
    "DEGRADED",
    "UNAVAILABLE",
    "PROVIDER_REQUIRED",
    "BLOCKED",
)

AVAILABILITY_STATES: tuple[str, ...] = (
    "AVAILABLE",
    "CONTRACT_READY",
    "PROVIDER_REQUIRED",
    "UNAVAILABLE",
    "BLOCKED",
)

# Binding mode: this round defines contracts only — never claim LIVE without a real bind.
MODES: tuple[str, ...] = (
    "CONTRACT",
    "PROVIDER_REQUIRED",
    "LIVE",  # reserved; only allowed when a real source bind is present
)

LEGAL_ACCESS_METHODS: frozenset[str] = frozenset(
    {
        "official_rest_api",
        "official_websocket",
        "official_bulk_download",
        "official_public_feed",
        "government_open_data",
        "central_bank_reference",
        "exchange_public_status",
        "founder_authorized_commercial_api",
        "local_fixture",
    }
)

HARD_BANS: tuple[str, ...] = (
    "no_member_exchange_write",
    "no_private_strategy_thresholds",
    "no_fabricated_live_values",
    "no_fake_live_mode",
    "no_fabricated_market_numbers",
    "no_paywall_scrape",
    "no_auth_bypass",
    "no_rate_limit_bypass",
    "no_customer_trading",
    "no_mainnet_trading",
    "no_real_money",
    "no_private_core_exposure",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_acceleration_report_edit",
    "local_staging_only",
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
        "entry_threshold",
        "exit_threshold",
        "proprietary_thresholds",
        "private_strategy_source",
        "position_size",
        "leverage",
        "exact_entry",
        "exact_stop",
        "order_id",
        "client_order_id",
        "exchange_order_id",
        "account_balance",
        "wallet_address",
        "place_order",
        "submit_order",
        "create_order",
        "execute_trade",
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
    "backend/nexus_pub17_global_market_contracts",
    "tools/public/run_pub17_global_market_contracts_gate.py",
    "tests/pub17_global_market_contracts",
    "artifacts/readiness/immutable/pub17_global_market_source_contracts",
)

REQUIRED_CONTRACT_FIELDS: tuple[str, ...] = (
    "domain",
    "source_id",
    "provider",
    "dataset",
    "access_method",
    "status",
    "license_type",
    "license_visibility",
    "commercial_use_allowed",
    "redistribution_allowed",
    "public_display_allowed",
    "provenance",
    "notes",
)

REQUIRED_DTO_FIELDS: tuple[str, ...] = (
    "schema",
    "schema_version",
    "domain",
    "source_id",
    "status",
    "mode",
    "freshness",
    "availability",
    "provenance",
    "license_visibility",
    "value",
    "unit",
    "as_of",
    "retrieved_at",
    "lineage_id",
    "fabricated",
)

PASS_RECOMMENDATION = "NEXUS_PUB17_GLOBAL_MARKET_SOURCE_CONTRACTS_PASS"
FAIL_RECOMMENDATION = "NEXUS_PUB17_GLOBAL_MARKET_SOURCE_CONTRACTS_FAIL"
