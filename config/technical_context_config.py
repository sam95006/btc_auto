import os


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


TECHNICAL_CONTEXT_ENABLED = _env_bool("NEXUS_TECHNICAL_CONTEXT_ENABLED", True)
KLINE_INTERVALS = tuple(
    item.strip()
    for item in os.getenv("NEXUS_TECH_KLINE_INTERVALS", "5m,15m").split(",")
    if item.strip()
) or ("5m", "15m")
KLINE_LIMIT = _env_int("NEXUS_TECH_KLINE_LIMIT", 80)

RSI_PERIOD = _env_int("NEXUS_TECH_RSI_PERIOD", 14)
EMA_FAST = _env_int("NEXUS_TECH_EMA_FAST", 20)
EMA_SLOW = _env_int("NEXUS_TECH_EMA_SLOW", 50)
ATR_PERIOD = _env_int("NEXUS_TECH_ATR_PERIOD", 14)

VOLUME_CONFIRM_RATIO = _env_float("NEXUS_TECH_VOLUME_CONFIRM_RATIO", 1.15)

REGIME_EXIT_ENABLED = _env_bool("NEXUS_REGIME_EXIT_ENABLED", True)
REGIME_EXIT_MIN_SCORE = _env_float("NEXUS_REGIME_EXIT_MIN_SCORE", 0.55)
REGIME_EXIT_MIN_PNL_PCT = _env_float("NEXUS_REGIME_EXIT_MIN_PNL_PCT", 0.03)
