import os

from config.revenue_target_config import REVENUE_GROWTH_MODE


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return float(default)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


# Peak-to-trough drawdown within the calendar month (futures equity).
MONTHLY_MAX_DRAWDOWN_PCT = _env_float("NEXUS_MONTHLY_MAX_DRAWDOWN_PCT", 0.10)
MONTHLY_DRAWDOWN_GUARD_ENABLED = _env_bool("NEXUS_MONTHLY_DRAWDOWN_GUARD", True)

# Volatility targeting for position sizing (ATR percentile from market context).
VOLATILITY_SIZING_ENABLED = _env_bool("NEXUS_VOLATILITY_SIZING", True)
VOLATILITY_TARGET_PERCENTILE = _env_float("NEXUS_VOLATILITY_TARGET_PERCENTILE", 0.45)
VOLATILITY_SIZE_FLOOR = _env_float("NEXUS_VOLATILITY_SIZE_FLOOR", 0.55)
VOLATILITY_SIZE_CAP = _env_float("NEXUS_VOLATILITY_SIZE_CAP", 1.15)
