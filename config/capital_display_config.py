"""Dashboard capital scope — USDT-M futures only, never coin-margined (dapi)."""

import os


def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = str(os.getenv(name, "") or "").strip()
    if not raw:
        return default
    values = tuple(item.strip().upper() for item in raw.split(",") if item.strip())
    return values or default


# USDT-M (U本位) demo futures API only. Coin-margined uses dapi/testnet.binancefuture.com — not wired.
FUTURES_CAPITAL_SCOPE = str(os.getenv("NEXUS_FUTURES_SCOPE", "usdt_m") or "usdt_m").strip().lower()
INCLUDE_COIN_MARGINED = str(os.getenv("NEXUS_INCLUDE_COIN_MARGINED", "0") or "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Treasury / trading capital display: default USDT only (excludes USDC, BTC in totals).
TREASURY_DISPLAY_ASSETS = _csv_env("NEXUS_TREASURY_ASSETS", ("USDT",))

DEFAULT_FUTURES_TESTNET_BASE = "https://demo-fapi.binance.com"
