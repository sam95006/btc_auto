"""Dashboard capital scope — USDT-M futures only, never coin-margined (dapi)."""

import os

# USDT-M (U本位) demo futures API only. Coin-margined uses dapi/testnet.binancefuture.com — not wired.
FUTURES_CAPITAL_SCOPE = str(os.getenv("NEXUS_FUTURES_SCOPE", "usdt_m") or "usdt_m").strip().lower()
INCLUDE_COIN_MARGINED = str(os.getenv("NEXUS_INCLUDE_COIN_MARGINED", "0") or "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

DEFAULT_FUTURES_TESTNET_BASE = "https://demo-fapi.binance.com"
