import os

from config.revenue_target_config import REVENUE_GROWTH_MODE


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return float(default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except Exception:
        return int(default)


GRID_TRADING_ENABLED = _env_bool("NEXUS_GRID_TRADING", True)
GRID_SIGNAL_INTERVAL_SEC = _env_int("NEXUS_GRID_INTERVAL_SEC", 40 if REVENUE_GROWTH_MODE else 60)
GRID_MAX_PROPOSALS_PER_TICK = _env_int("NEXUS_GRID_MAX_PROPOSALS", 3)
GRID_LOOKBACK_TICKS = _env_int("NEXUS_GRID_LOOKBACK", 24)
GRID_SPACING_PCT = _env_float("NEXUS_GRID_SPACING_PCT", 0.0035)
GRID_RANGE_MAX_DEVIATION_PCT = _env_float("NEXUS_GRID_RANGE_MAX_DEV", 0.018)
GRID_MAX_VOLATILITY_PERCENTILE = _env_float("NEXUS_GRID_MAX_VOL_PCT", 0.72)
GRID_MIN_CONFIDENCE = _env_float("NEXUS_GRID_MIN_CONFIDENCE", 0.48)
GRID_CAPITAL_POOL_FRACTION = _env_float("NEXUS_GRID_CAPITAL_FRACTION", 0.35)
