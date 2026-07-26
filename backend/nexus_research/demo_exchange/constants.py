"""Phase 6.6 — Bybit Demo READ-ONLY constants (no write endpoints)."""
from __future__ import annotations

# Hard allowlist — Demo REST only. Future private WS noted but NOT enabled.
DEMO_REST_BASE_URL = "https://api-demo.bybit.com"
DEMO_WS_PRIVATE_NOTE = "wss://stream-demo.bybit.com"  # documentation only; WS trading disabled

FORBIDDEN_BASE_URLS = frozenset(
    {
        "https://api.bybit.com",
        "http://api.bybit.com",
        "https://api-testnet.bybit.com",
        "http://api-testnet.bybit.com",
    }
)

# Account identity — never mix with paper ledger.
ACCOUNT_PAPER_MAIN_V1 = "NEXUS_PAPER_MAIN_V1"
ACCOUNT_BYBIT_DEMO = "BYBIT_DEMO_ACCOUNT"

# Credential env keys (presence only; never log values).
ENV_API_KEY = "BYBIT_DEMO_API_KEY"
ENV_API_SECRET = "BYBIT_DEMO_API_SECRET"

# GET-only private read paths (Bybit v5).
ALLOWED_GET_PATHS = frozenset(
    {
        "/v5/account/wallet-balance",
        "/v5/position/list",
        "/v5/order/realtime",
        "/v5/order/history",
        "/v5/execution/list",
        "/v5/position/closed-pnl",
    }
)

# Explicitly forbidden write / mutation path fragments.
FORBIDDEN_WRITE_PATH_FRAGMENTS = (
    "/v5/order/create",
    "/v5/order/amend",
    "/v5/order/cancel",
    "/v5/order/cancel-all",
    "/v5/position/set-leverage",
    "/v5/position/trading-stop",
    "/v5/position/close",
    "/v5/asset/transfer",
    "/v5/asset/withdraw",
    "/v5/asset/deposit",
    "apply_demo_money",
    "create_order",
    "amend_order",
    "cancel_order",
)

DEFAULT_CATEGORY = "linear"
DEFAULT_ACCOUNT_TYPE = "UNIFIED"
DEFAULT_COIN = "USDT"
HTTP_TIMEOUT_SEC = 15.0
STALE_MS_DEFAULT = 120_000
FINGERPRINT_LEN = 8  # irreversible, max 6–8 chars
RECV_WINDOW_MS = "5000"

PHASE = "6.6"
RESEARCH_ONLY = True
WRITE_ALLOWED = False
