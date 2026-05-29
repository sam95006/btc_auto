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
        return default


MARKET_NEUTRAL_ENABLED = _env_bool("NEXUS_MARKET_NEUTRAL_ENABLED", True)
MARKET_NEUTRAL_CAPITAL_PCT = _env_float("NEXUS_MARKET_NEUTRAL_CAPITAL_PCT", 0.15)
MARKET_NEUTRAL_CAPITAL_PCT_MAX = _env_float("NEXUS_MARKET_NEUTRAL_CAPITAL_PCT_MAX", 0.20)
MARKET_NEUTRAL_PAUSE_RADAR = _env_bool("NEXUS_MARKET_NEUTRAL_PAUSE_RADAR", True)
MARKET_NEUTRAL_MIN_FUNDING_RATE = _env_float("NEXUS_MARKET_NEUTRAL_MIN_FUNDING_RATE", 0.0003)
MARKET_NEUTRAL_INTERVAL_SEC = int(os.getenv("NEXUS_MARKET_NEUTRAL_INTERVAL_SEC", "3600" if not REVENUE_GROWTH_MODE else "1800"))
MARKET_NEUTRAL_MAX_POSITIONS = int(os.getenv("NEXUS_MARKET_NEUTRAL_MAX_POSITIONS", "2"))
MARKET_NEUTRAL_LEG_MARGIN_MIN = _env_float("NEXUS_MARKET_NEUTRAL_LEG_MARGIN_MIN", 25.0)
MARKET_NEUTRAL_HEDGE_TIMEOUT_MS = int(os.getenv("NEXUS_MARKET_NEUTRAL_HEDGE_TIMEOUT_MS", "500"))
