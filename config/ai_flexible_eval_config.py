"""Holistic LLM evaluation for entries and exits (all market data → trade actions)."""

import os

from config.ai_trading_config import AI_LED_MIN_CONFIDENCE


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


AI_FLEX_EVAL_ENABLED = _env_bool("NEXUS_AI_FLEX_EVAL", True)
AI_FLEX_EXIT_ENABLED = _env_bool("NEXUS_AI_FLEX_EXIT", True)
# 全 AI 主導：進場只走 flex 評估；出場 AI 優先、規則 TP 讓路
AI_FLEX_PRIMARY_MODE = _env_bool("NEXUS_AI_FLEX_PRIMARY", True)
AI_FLEX_EXIT_PRIMARY = _env_bool("NEXUS_AI_FLEX_EXIT_PRIMARY", True)
# LLM 直接決定 leverage + margin（仍經 autonomy_bounds 硬上限）
AI_FLEX_SIZING_FROM_LLM = _env_bool("NEXUS_AI_FLEX_SIZING", True)
AI_FLEX_AUTO_PROFIT_ENABLED = _env_bool("NEXUS_AI_FLEX_AUTO_PROFIT", True)
AI_FLEX_MIN_CONFIDENCE = _env_float("NEXUS_AI_FLEX_MIN_CONFIDENCE", max(0.40, AI_LED_MIN_CONFIDENCE - 0.05))
AI_FLEX_EXIT_MIN_CONFIDENCE = _env_float("NEXUS_AI_FLEX_EXIT_MIN_CONFIDENCE", 0.58)
AI_FLEX_MAX_PROPOSALS = int(_env_float("NEXUS_AI_FLEX_MAX_PROPOSALS", 3))
AI_FLEX_MAX_LEVERAGE = _env_float("NEXUS_AI_FLEX_MAX_LEVERAGE", 100.0)
AI_FLEX_HEURISTIC_FALLBACK = _env_bool("NEXUS_AI_FLEX_HEURISTIC_FALLBACK", True)
AI_FLEX_AUTO_PROFIT_PCT = _env_float("NEXUS_AI_FLEX_AUTO_PROFIT_PCT", 12.0)
