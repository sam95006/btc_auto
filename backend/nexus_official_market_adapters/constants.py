"""V18-A Official Read-Only Market Adapters — constants and hard bans."""
from __future__ import annotations

SCHEMA = "v18_a_official_readonly_market_adapters_v1"
ENVELOPE_SCHEMA = "v18_a_market_observation_envelope_v1"
SCHEMA_VERSION = 1
LANE = "V18-A"
LANE_NAME = "OFFICIAL_READONLY_MARKET_ADAPTERS"
BRANCH = "feature/v18-official-readonly-market-adapters"
BASE_COMMIT = "324e52f0573d7e3ad32feb2968274a52b8d8da75"
ARTIFACT_REL = "artifacts/readiness/immutable/v18_official_readonly_market_adapters"

# Honest mode labels — never call FIXTURE payloads LIVE.
DATA_MODE_LIVE_READ_ONLY = "LIVE_READ_ONLY"
DATA_MODE_FIXTURE = "FIXTURE"
DATA_MODES = frozenset({DATA_MODE_LIVE_READ_ONLY, DATA_MODE_FIXTURE})

# Observation quality — never fabricate zeros for missing fields.
QUALITY_OK = "OK"
QUALITY_DEGRADED = "DEGRADED"
QUALITY_STALE = "STALE"
QUALITY_UNAVAILABLE = "UNAVAILABLE"
QUALITY_STATES = frozenset(
    {QUALITY_OK, QUALITY_DEGRADED, QUALITY_STALE, QUALITY_UNAVAILABLE}
)

CAPABILITIES: tuple[str, ...] = (
    "instrument_catalog",
    "ticker",
    "mark_index_price",
    "ohlcv",
    "public_trades",
    "funding",
    "open_interest",
    "order_book_summary",
    "liquidation",
    "listing_status",
    "contract_specs",
)

OFFICIAL_READ_ADAPTER_IDS: tuple[str, ...] = (
    "bybit_public_v5",
    "binance_usdm_public",
)

# Contract-only providers — never emit fabricated Live values.
CONTRACT_ONLY_PROVIDER_IDS: tuple[str, ...] = (
    "okx_public",
    "coinbase_exchange_public",
    "kraken_public",
)

HARD_BAN_SCRAPE_PROVIDERS: frozenset[str] = frozenset(
    {"glassnode", "coinglass", "messari"}
)

HARD_BANS: tuple[str, ...] = (
    "no_glassnode_paywall_scrape",
    "no_coinglass_paywall_scrape",
    "no_messari_paywall_scrape",
    "no_rate_limit_bypass",
    "no_unauthorized_data",
    "no_fill_missing_with_zero",
    "no_treat_rest_as_always_correct",
    "no_api_key_for_public_endpoints",
    "no_secret",
    "no_account_order_wallet_endpoints",
    "no_exchange_write",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_demo_mainnet_real_money",
    "no_acceleration_report_edit",
)

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_SECONDS = 0.05
DEFAULT_RATE_LIMIT_PER_SECOND = 8.0
DEFAULT_CIRCUIT_FAILURE_THRESHOLD = 5
DEFAULT_FRESHNESS_STALE_MS = 60_000

BLOCKED_AUTH_HEADERS: frozenset[str] = frozenset(
    {
        "authorization",
        "x-bapi-api-key",
        "x-bapi-sign",
        "x-bapi-timestamp",
        "x-bapi-recv-window",
        "x-mbx-apikey",
        "api-key",
        "api-sign",
        "api-timestamp",
        "api-signature",
        "secret",
        "api_secret",
    }
)

WRITE_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Path substrings that imply account / private / write surfaces.
ACCOUNT_PATH_MARKERS: frozenset[str] = frozenset(
    {
        "/account",
        "/order",
        "/orders",
        "/wallet",
        "/position",
        "/positions",
        "/user",
        "/private",
        "/trade/order",
        "/sapi/",
        "/fapi/v1/order",
        "/fapi/v1/position",
        "/fapi/v2/position",
        "/v5/order",
        "/v5/account",
        "/v5/position",
        "/v5/user",
    }
)
