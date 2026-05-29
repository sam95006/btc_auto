"""Rule-based confidence matrix (0-100) + dynamic allocation tiers."""

import os

from config.ai_trading_config import AI_LED_MIN_CONFIDENCE


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return default


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


CONFIDENCE_MATRIX_ENABLED = _env_bool("NEXUS_CONFIDENCE_MATRIX_ENABLED", True)
CONFIDENCE_MATRIX_MIN_SCORE = _env_float("NEXUS_CONFIDENCE_MATRIX_MIN_SCORE", max(55.0, AI_LED_MIN_CONFIDENCE * 100))

SCORE_TIER_LOW_MAX = 69.0
SCORE_TIER_MID_MAX = 85.0

TIER_LOW_MARGIN_MULT = _env_float("NEXUS_CONFIDENCE_TIER_LOW_MARGIN_MULT", 0.5)
TIER_MID_MARGIN_MULT = _env_float("NEXUS_CONFIDENCE_TIER_MID_MARGIN_MULT", 1.0)
TIER_HIGH_MARGIN_MULT = _env_float("NEXUS_CONFIDENCE_TIER_HIGH_MARGIN_MULT", 1.0)

TIER_LOW_LEVERAGE = _env_float("NEXUS_CONFIDENCE_TIER_LOW_LEVERAGE", 2.0)
TIER_MID_LEVERAGE = _env_float("NEXUS_CONFIDENCE_TIER_MID_LEVERAGE", 5.0)
TIER_HIGH_LEVERAGE = _env_float("NEXUS_CONFIDENCE_TIER_HIGH_LEVERAGE", 8.0)

BASE_MARGIN_RADAR = _env_float("NEXUS_CONFIDENCE_BASE_MARGIN_RADAR", 28.0)
BASE_MARGIN_CORE = _env_float("NEXUS_CONFIDENCE_BASE_MARGIN_CORE", 35.0)

ABSOLUTE_MAX_LEVERAGE = _env_float("NEXUS_ABSOLUTE_MAX_LEVERAGE", 10.0)
ABSOLUTE_MAX_MARGIN_PCT = _env_float("NEXUS_ABSOLUTE_MAX_MARGIN_PCT", 0.20)
ABSOLUTE_MAX_STOP_LOSS_PCT = _env_float("NEXUS_ABSOLUTE_MAX_STOP_LOSS_PCT", 0.02)

POSTMORTEM_MACRO_PENALTY = _env_float("NEXUS_POSTMORTEM_MACRO_PENALTY", 30.0)
