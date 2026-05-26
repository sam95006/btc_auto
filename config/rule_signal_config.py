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


RULE_SIGNAL_BRIDGE_ENABLED = _env_bool("NEXUS_RULE_SIGNAL_BRIDGE", True)
RULE_SIGNAL_INTERVAL_SEC = _env_int("NEXUS_RULE_SIGNAL_INTERVAL_SEC", 30 if REVENUE_GROWTH_MODE else 60)
RULE_SIGNAL_MIN_CONFIDENCE = _env_float("NEXUS_RULE_SIGNAL_MIN_CONFIDENCE", 0.46)
RULE_SIGNAL_MOMENTUM_PCT = _env_float("NEXUS_RULE_SIGNAL_MOMENTUM_PCT", 0.0010 if REVENUE_GROWTH_MODE else 0.0012)
RULE_SIGNAL_MAX_PROPOSALS = _env_int("NEXUS_RULE_SIGNAL_MAX_PROPOSALS", 3 if REVENUE_GROWTH_MODE else 2)
