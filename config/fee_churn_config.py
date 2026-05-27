import os

from config.growth_mode_config import BOLD_TESTNET_ENABLED


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


# Binance futures taker ~0.04% per side; round-trip ~0.08% of notional.
FEE_CHURN_GUARD_ENABLED = _env_bool("NEXUS_FEE_CHURN_GUARD", True)
FUTURES_TAKER_FEE_BPS = _env_float("NEXUS_FUTURES_TAKER_FEE_BPS", 4.0)
FEE_EDGE_MULTIPLIER = _env_float("NEXUS_FEE_EDGE_MULTIPLIER", 3.5)

_default_min_margin = 45.0 if BOLD_TESTNET_ENABLED else 35.0
MIN_MARGIN_USD = _env_float("NEXUS_MIN_MARGIN_USD", _default_min_margin)
MIN_NOTIONAL_USD = _env_float("NEXUS_MIN_NOTIONAL_USD", 280.0)

MIN_HOLD_SECONDS_BEFORE_EXIT = _env_int("NEXUS_MIN_HOLD_SECONDS", 180)
MIN_SYMBOL_REOPEN_SECONDS = _env_int("NEXUS_SYMBOL_REOPEN_COOLDOWN_SEC", 300)
MIN_SECONDS_BETWEEN_PARTIALS = _env_int("NEXUS_MIN_PARTIAL_EXIT_INTERVAL_SEC", 120)

R_EXIT_MIN_NET_PROFIT_USD = _env_float("NEXUS_R_EXIT_MIN_NET_PROFIT_USD", 0.55)
AI_EXIT_MIN_ABS_PNL_USD = _env_float("NEXUS_AI_EXIT_MIN_ABS_PNL_USD", 0.45)
AI_LIQ_EXIT_REQUIRES_CRITICAL = _env_bool("NEXUS_AI_LIQ_EXIT_REQUIRES_CRITICAL", True)
