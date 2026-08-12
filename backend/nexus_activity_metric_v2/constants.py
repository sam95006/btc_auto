"""Official Activity Metric V2 — constants and hard bans.

Isolated package: feature/nexus-activity-metric-v2-isolated
Does NOT wire into running Shadow campaigns or lower Gate thresholds.
"""
from __future__ import annotations

SCHEMA = "v18_2_9_official_activity_metric_v2"
SCHEMA_VERSION = 2
PACKAGE = "nexus_activity_metric_v2"
BRANCH = "feature/nexus-activity-metric-v2-isolated"
BASE_COMMIT = "07ec7641f86e2a1324fe88a98a16d417ba34f885"

# Quality states — partial warmup must be INSUFFICIENT_HISTORY, never zeroed LIVE.
ACTIVITY_QUALITY_STATES: tuple[str, ...] = (
    "LIVE",
    "INSUFFICIENT_HISTORY",
    "STALE",
    "UNAVAILABLE",
    "DEGRADED",
)

SOURCE_REST = "bybit_public_rest_recent_trade"
SOURCE_WS = "bybit_public_ws_publicTrade"
SOURCE_REPLAY = "checkpoint_replay"
SOURCE_SYNTHETIC = "synthetic_fixture"

BYBIT_REST_HOST = "api.bybit.com"
BYBIT_REST_BASE = "https://api.bybit.com"
BYBIT_RECENT_TRADE_PATH = "/v5/market/recent-trade"
BYBIT_PUBLIC_WS_URL = "wss://stream.bybit.com/v5/public/linear"
BYBIT_PUBLIC_TRADE_TOPIC_PREFIX = "publicTrade"

DEFAULT_WINDOW_MS = 86_400_000  # 24h rolling window
DEFAULT_STALE_MS = 120_000
DEFAULT_MAX_CLOCK_SKEW_MS = 5_000
DEFAULT_RATE_LIMIT_PER_SECOND = 5.0
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_SECONDS = 0.1

# Explicit field names — NEVER alias volume24h/turnover24h as trade_count_24h.
METRIC_TRADE_COUNT_WINDOW = "trade_count_window"
METRIC_TRADE_NOTIONAL_WINDOW = "trade_notional_window"
METRIC_UNIQUE_TRADE_COUNT = "unique_trade_count"
METRIC_BUY_SELL_ACTIVITY = "buy_sell_activity"

# Gate contract documentation (see gate_contract.py).
GATE_FIELD_TRADE_COUNT_24H = "trade_count_24h"
PROXY_METRIC_VERSION = "activity_metric_v2_trade_count_window"
PROXY_FORBIDDEN_SAME_FIELD = True

HARD_BANS: tuple[str, ...] = (
    "no_silent_volume24h_as_trade_count_24h",
    "no_silent_turnover24h_as_trade_count_24h",
    "no_lower_eligibility_gates",
    "no_shadow_campaign_mutation",
    "no_demo_orders",
    "no_mainnet_orders",
    "no_exchange_write",
    "no_zero_fill_missing_warmup",
    "no_production_ui_touch",
)
