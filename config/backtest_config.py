"""Binance kline research / OOS gate (single-exchange testnet)."""

import os


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return default


KLINE_BACKTEST_ENABLED = _env_bool("NEXUS_KLINE_BACKTEST_ENABLED", True)
KLINE_INTERVAL = str(os.getenv("NEXUS_KLINE_BACKTEST_INTERVAL", "15m") or "15m").strip()
KLINE_LOOKBACK = _env_int("NEXUS_KLINE_BACKTEST_LOOKBACK", 120)
KLINE_MIN_BARS = _env_int("NEXUS_KLINE_BACKTEST_MIN_BARS", 40)
KLINE_MIN_EDGE_SCORE = _env_float("NEXUS_KLINE_BACKTEST_MIN_EDGE", 0.52)
KLINE_FEE_BPS_PER_SIDE = _env_float("NEXUS_KLINE_BACKTEST_FEE_BPS", 4.0)
KLINE_SLIPPAGE_BPS = _env_float("NEXUS_KLINE_BACKTEST_SLIPPAGE_BPS", 6.0)

WALK_FORWARD_MIN_POSITIVE_RATIO = _env_float("NEXUS_WALK_FORWARD_MIN_POSITIVE_RATIO", 0.40)
WALK_FORWARD_MIN_LATEST_WIN_RATE = _env_float("NEXUS_WALK_FORWARD_MIN_LATEST_WIN_RATE", 0.38)

RESEARCH_GATE_ENABLED = _env_bool("NEXUS_RESEARCH_GATE_ENABLED", True)
RESEARCH_GATE_REQUIRE_FOR_LEARNING = _env_bool("NEXUS_LEARNING_REQUIRE_RESEARCH_PASS", True)
RESEARCH_GATE_BLOCK_WHEN_FAIL = _env_bool("NEXUS_RESEARCH_GATE_BLOCK_ENTRIES", False)
