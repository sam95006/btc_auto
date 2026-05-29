"""AI auto-trade: margin & leverage scale with model confidence (0–1)."""

import os

from config.ai_trading_config import AI_LED_MIN_CONFIDENCE
from config.autonomy_bounds_config import HARD_MAX_LEVERAGE, HARD_MIN_LEVERAGE, HARD_MAX_MARGIN_USD, HARD_MIN_MARGIN_USD
from config.fee_churn_config import MIN_MARGIN_USD
from config.radar_dispatch_config import RADAR_MAX_LEVERAGE, RADAR_MIN_MARGIN


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


AI_CONFIDENCE_SIZING_ENABLED = _env_bool("NEXUS_AI_CONFIDENCE_SIZING", True)

# At min_confidence -> low tier; at 1.0 -> high tier
AI_CONFIDENCE_MIN = _env_float("NEXUS_AI_CONFIDENCE_SIZING_MIN", AI_LED_MIN_CONFIDENCE)
AI_CONFIDENCE_MARGIN_MULT_MIN = _env_float("NEXUS_AI_CONFIDENCE_MARGIN_MULT_MIN", 0.45)
AI_CONFIDENCE_MARGIN_MULT_MAX = _env_float("NEXUS_AI_CONFIDENCE_MARGIN_MULT_MAX", 1.0)
AI_CONFIDENCE_LEVERAGE_MIN = _env_float("NEXUS_AI_CONFIDENCE_LEVERAGE_MIN", max(HARD_MIN_LEVERAGE, 2.0))
AI_CONFIDENCE_LEVERAGE_MAX = _env_float(
    "NEXUS_AI_CONFIDENCE_LEVERAGE_MAX",
    min(float(RADAR_MAX_LEVERAGE), float(HARD_MAX_LEVERAGE), 10.0),
)

# Base margin before confidence multiplier (USDT)
AI_CONFIDENCE_BASE_MARGIN_RADAR = _env_float("NEXUS_AI_CONFIDENCE_BASE_MARGIN_RADAR", max(RADAR_MIN_MARGIN, 28.0))
AI_CONFIDENCE_BASE_MARGIN_CORE = _env_float("NEXUS_AI_CONFIDENCE_BASE_MARGIN_CORE", max(MIN_MARGIN_USD, 35.0))

# Optional: scale base from deployable pool (0 = use fixed base only)
AI_CONFIDENCE_DEPLOYABLE_PCT_RADAR = _env_float("NEXUS_AI_CONFIDENCE_DEPLOYABLE_PCT_RADAR", 0.04)
AI_CONFIDENCE_DEPLOYABLE_PCT_CORE = _env_float("NEXUS_AI_CONFIDENCE_DEPLOYABLE_PCT_CORE", 0.06)
AI_CONFIDENCE_DEPLOYABLE_CAP_RADAR = _env_float("NEXUS_AI_CONFIDENCE_DEPLOYABLE_CAP_RADAR", 120.0)
AI_CONFIDENCE_DEPLOYABLE_CAP_CORE = _env_float("NEXUS_AI_CONFIDENCE_DEPLOYABLE_CAP_CORE", 150.0)

AI_CONFIDENCE_MARGIN_FLOOR = max(HARD_MIN_MARGIN_USD, MIN_MARGIN_USD)
AI_CONFIDENCE_MARGIN_CEILING = min(HARD_MAX_MARGIN_USD, 500.0)
