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


FUNDING_ARB_ENABLED = _env_bool("NEXUS_FUNDING_ARB", True)
FUNDING_ARB_INTERVAL_SEC = _env_int("NEXUS_FUNDING_ARB_INTERVAL_SEC", 50 if REVENUE_GROWTH_MODE else 90)
FUNDING_ARB_MAX_PROPOSALS = _env_int("NEXUS_FUNDING_ARB_MAX_PROPOSALS", 3)
FUNDING_ARB_MIN_ABS_RATE = _env_float("NEXUS_FUNDING_ARB_MIN_ABS", 0.00025)
FUNDING_ARB_MIN_CONFIDENCE = _env_float("NEXUS_FUNDING_ARB_MIN_CONFIDENCE", 0.50)
FUNDING_ARB_MAX_LEVERAGE = _env_float("NEXUS_FUNDING_ARB_MAX_LEVERAGE", 8.0)
FUNDING_ARB_CAPITAL_FRACTION = _env_float("NEXUS_FUNDING_ARB_CAPITAL_FRACTION", 0.25)
