import os

from config.growth_mode_config import BOLD_TESTNET_ENABLED


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return int(default)
    try:
        return int(float(str(raw).strip()))
    except Exception:
        return int(default)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return float(default)
    try:
        return float(str(raw).strip())
    except Exception:
        return float(default)


# Testnet bold mode: learning shrinks size/leverage instead of hard-pausing all entries.
LEARNING_HARD_PAUSE_ENABLED = _env_bool(
    "NEXUS_LEARNING_HARD_PAUSE",
    not BOLD_TESTNET_ENABLED,
)

MAX_CONFIDENCE_PENALTY = 0.4
LOSS_RATE_PENALTY_THRESHOLD = 0.55
CONSECUTIVE_LOSS_SOFT_BLOCK = _env_int("NEXUS_LEARNING_SOFT_BLOCK_LOSSES", 3)
CONSECUTIVE_LOSS_HARD_BLOCK = _env_int(
    "NEXUS_LEARNING_HARD_BLOCK_LOSSES",
    8 if BOLD_TESTNET_ENABLED else 5,
)
SYMBOL_COOLDOWN_LOSS_COUNT = _env_int("NEXUS_LEARNING_SYMBOL_COOLDOWN_LOSSES", 3)
SYMBOL_COOLDOWN_WINDOW = _env_int("NEXUS_LEARNING_SYMBOL_COOLDOWN_WINDOW", 6)
SYMBOL_COOLDOWN_SECONDS = _env_int(
    "NEXUS_LEARNING_SYMBOL_COOLDOWN_SECONDS",
    3600 if BOLD_TESTNET_ENABLED else 6 * 60 * 60,
)
LIQUIDATION_SYMBOL_COOLDOWN_SECONDS = _env_int(
    "NEXUS_LIQUIDATION_SYMBOL_COOLDOWN_SECONDS",
    4 * 60 * 60,
)
# Strong liquidations: temporary pause + stricter re-entry rules, NOT permanent symbol blacklist.
LIQUIDATION_PERMANENT_BLACKLIST = _env_bool("NEXUS_LIQUIDATION_PERMANENT_BLACKLIST", False)
LIQUIDATION_REENTRY_MIN_CONFIDENCE = _env_float("NEXUS_LIQUIDATION_REENTRY_MIN_CONFIDENCE", 0.72)
LIQUIDATION_REENTRY_LEVERAGE_CAP = _env_int("NEXUS_LIQUIDATION_REENTRY_LEVERAGE_CAP", 5)
LIQUIDATION_REENTRY_SIZE_MULT = _env_float("NEXUS_LIQUIDATION_REENTRY_SIZE_MULT", 0.55)
HIGH_LEVERAGE_FAILURE_THRESHOLD = 20
HIGH_LEVERAGE_PENALTY_STEP = 0.03
MAX_HIGH_LEVERAGE_PENALTY = 0.15
BASE_POSITION_SIZE_MULTIPLIER_FLOOR = 0.35
BASE_AGGRESSION_MULTIPLIER_FLOOR = 0.45
FAILURE_FOCUS_BLOCK_MAP = {
    "low_liquidity": "low_liquidity",
    "news_conflict": "news_conflict",
    "whale_reversal": "whale_conflict",
    "bad_market_regime": "market_regime",
}
