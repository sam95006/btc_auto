"""Hard safety bounds for AI / learning parameter changes (cannot be overridden by LLM)."""

import os

from config.radar_dispatch_config import RADAR_MAX_OPEN_POSITIONS


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except Exception:
        return default


HARD_MAX_LEVERAGE = _env_float("NEXUS_HARD_MAX_LEVERAGE", 10.0)
HARD_MIN_LEVERAGE = _env_float("NEXUS_HARD_MIN_LEVERAGE", 1.0)
HARD_MAX_STOP_LOSS_PCT = _env_float("NEXUS_HARD_MAX_STOP_LOSS_PCT", 0.03)
HARD_MIN_MARGIN_USD = _env_float("NEXUS_HARD_MIN_MARGIN_USD", 10.0)
HARD_MAX_MARGIN_USD = _env_float("NEXUS_HARD_MAX_MARGIN_USD", 500.0)
HARD_MAX_OPEN_POSITIONS = _env_int("NEXUS_HARD_MAX_OPEN_POSITIONS", min(8, max(1, RADAR_MAX_OPEN_POSITIONS)))
HARD_MIN_POSITION_SIZE_MULT = _env_float("NEXUS_HARD_MIN_POSITION_SIZE_MULT", 0.25)
HARD_MAX_POSITION_SIZE_MULT = _env_float("NEXUS_HARD_MAX_POSITION_SIZE_MULT", 1.0)
HARD_MAX_SIGNAL_WEIGHT_ADJ = _env_float("NEXUS_HARD_MAX_SIGNAL_WEIGHT_ADJ", 0.15)

DEFAULT_SAFE_LEVERAGE = _env_float("NEXUS_DEFAULT_SAFE_LEVERAGE", 5.0)
DEFAULT_SAFE_STOP_LOSS_PCT = _env_float("NEXUS_DEFAULT_SAFE_STOP_LOSS_PCT", 0.02)
DEFAULT_SAFE_POSITION_SIZE_MULT = _env_float("NEXUS_DEFAULT_SAFE_POSITION_SIZE_MULT", 0.85)

ABSOLUTE_MAX_MARGIN_PCT = _env_float("NEXUS_ABSOLUTE_MAX_MARGIN_PCT", 0.20)
