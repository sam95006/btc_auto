"""Limit orders, TCA, TradingView webhook (Binance futures testnet)."""

import os


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return default


LIMIT_ORDERS_ENABLED = _env_bool("NEXUS_USE_LIMIT_ORDERS", False)
LIMIT_ORDER_OFFSET_BPS = _env_float("NEXUS_LIMIT_ORDER_OFFSET_BPS", 8.0)
LIMIT_ORDER_FALLBACK_MARKET = _env_bool("NEXUS_LIMIT_FALLBACK_MARKET", True)

TCA_ENABLED = _env_bool("NEXUS_TCA_ENABLED", True)
TCA_MAX_SLIPPAGE_BPS = _env_float("NEXUS_TCA_MAX_SLIPPAGE_BPS", 25.0)

TRAILING_EXIT_ADVISORY = _env_bool("NEXUS_TRAILING_EXIT_ADVISORY", True)
TRAILING_ACTIVATION_R = _env_float("NEXUS_TRAILING_ACTIVATION_R", 0.55)
TRAILING_CALLBACK_R = _env_float("NEXUS_TRAILING_CALLBACK_R", 0.25)

TRADINGVIEW_WEBHOOK_ENABLED = _env_bool("NEXUS_TRADINGVIEW_WEBHOOK_ENABLED", True)
TRADINGVIEW_WEBHOOK_SECRET = str(os.getenv("NEXUS_TRADINGVIEW_WEBHOOK_SECRET", "") or "").strip()
