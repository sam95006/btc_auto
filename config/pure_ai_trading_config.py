"""Pure AI trader mode — LLM decides entries/exits; only hard safety caps remain."""

import os

from backend.trading.sandbox_mode import sandbox_active


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


# Master switch: full AI trader (explicit opt-in via NEXUS_PURE_AI_MODE=1 on testnet).
PURE_AI_MODE = _env_bool("NEXUS_PURE_AI_MODE", False)
PURE_AI_LLM_ONLY = _env_bool("NEXUS_PURE_AI_LLM_ONLY", True)
PURE_AI_BYPASS_VALIDATION = _env_bool("NEXUS_PURE_AI_BYPASS_VALIDATION", True)
PURE_AI_BYPASS_FEE_CHURN = _env_bool("NEXUS_PURE_AI_BYPASS_FEE_CHURN", True)
PURE_AI_BYPASS_GROWTH_BLOCKS = _env_bool("NEXUS_PURE_AI_BYPASS_GROWTH_BLOCKS", True)
PURE_AI_SKIP_RULE_EXITS = _env_bool("NEXUS_PURE_AI_SKIP_RULE_EXITS", True)
PURE_AI_MIN_MARGIN_USD = _env_float("NEXUS_PURE_AI_MIN_MARGIN_USD", 80.0)
PURE_AI_MAX_MARGIN_USD = _env_float("NEXUS_PURE_AI_MAX_MARGIN_USD", 120.0)
PURE_AI_TARGET_NOTIONAL_USD = _env_float("NEXUS_PURE_AI_TARGET_NOTIONAL_USD", 800.0)
PURE_AI_RADAR_MARGIN_CAP_FRAC = _env_float("NEXUS_PURE_AI_RADAR_MARGIN_CAP_FRAC", 0.40)
PURE_AI_DEFAULT_LEVERAGE = _env_float("NEXUS_PURE_AI_DEFAULT_LEVERAGE", 25.0)
PURE_AI_MAX_LEVERAGE = _env_float("NEXUS_PURE_AI_MAX_LEVERAGE", 25.0)
PURE_AI_HARD_EXIT_ENABLED = _env_bool("NEXUS_PURE_AI_HARD_EXIT", True)
PURE_AI_TP_PARTIAL_PCT = _env_float("NEXUS_PURE_AI_TP_PARTIAL_PCT", 12.0)
PURE_AI_TP_FULL_PCT = _env_float("NEXUS_PURE_AI_TP_FULL_PCT", 28.0)
PURE_AI_SL_PCT_ON_MARGIN = _env_float("NEXUS_PURE_AI_SL_PCT_ON_MARGIN", 16.0)
PURE_AI_TP_ABS_USD = _env_float("NEXUS_PURE_AI_TP_ABS_USD", 10.0)
PURE_AI_SL_ABS_USD = _env_float("NEXUS_PURE_AI_SL_ABS_USD", 12.0)
PURE_AI_PARTIAL_FRACTION = _env_float("NEXUS_PURE_AI_PARTIAL_FRACTION", 0.5)
PURE_AI_MAX_PROPOSALS_PER_TICK = int(_env_float("NEXUS_PURE_AI_MAX_PROPOSALS", 6))
PURE_AI_MIN_CONFIDENCE = _env_float("NEXUS_PURE_AI_MIN_CONFIDENCE", 0.15)
PURE_AI_FAST_SCAN = _env_bool("NEXUS_PURE_AI_FAST_SCAN", True)
PURE_AI_LLM_REFRESH_SECONDS = int(_env_float("NEXUS_PURE_AI_LLM_REFRESH_SECONDS", 3))
PURE_AI_HEURISTIC_HEARTBEAT = _env_bool("NEXUS_PURE_AI_HEURISTIC_HEARTBEAT", True)
PURE_AI_BYPASS_RADAR_COOLDOWN = _env_bool("NEXUS_PURE_AI_BYPASS_RADAR_COOLDOWN", True)
PURE_AI_RADAR_FALLBACK_MAX = int(_env_float("NEXUS_PURE_AI_RADAR_FALLBACK_MAX", 4))
PURE_AI_HEARTBEAT_SYMBOLS_MAX = int(_env_float("NEXUS_PURE_AI_HEARTBEAT_MAX", 3))
PURE_AI_STALE_SAFETY_HOURS = _env_float("NEXUS_PURE_AI_STALE_SAFETY_HOURS", 24.0)
PURE_AI_DEBATE_GATE = _env_bool("NEXUS_PURE_AI_DEBATE_GATE", False)
PURE_AI_DEBATE_HARD_VETO = _env_bool("NEXUS_PURE_AI_DEBATE_HARD_VETO", False)
PURE_AI_PYRAMID_ENABLED = _env_bool("NEXUS_PURE_AI_PYRAMID", True)
PURE_AI_PYRAMID_MIN_PNL_PCT = _env_float("NEXUS_PURE_AI_PYRAMID_MIN_PNL_PCT", 12.0)
PURE_AI_PYRAMID_MIN_PNL_USD = _env_float("NEXUS_PURE_AI_PYRAMID_MIN_PNL_USD", 25.0)
PURE_AI_PYRAMID_MARGIN_MULT = _env_float("NEXUS_PURE_AI_PYRAMID_MARGIN_MULT", 0.55)
PURE_AI_PYRAMID_MAX_ADDS = int(_env_float("NEXUS_PURE_AI_PYRAMID_MAX_ADDS", 2))
PURE_AI_RADAR_FALLBACK = _env_bool("NEXUS_PURE_AI_RADAR_FALLBACK", True)
PURE_AI_REQUIRE_MIN_PROPOSALS = _env_bool("NEXUS_PURE_AI_REQUIRE_MIN_PROPOSALS", True)
PURE_AI_MAX_ENTRIES_PER_TICK = int(_env_float("NEXUS_PURE_AI_MAX_ENTRIES_PER_TICK", 2))
PURE_AI_MAX_PYRAMID_PER_TICK = int(_env_float("NEXUS_PURE_AI_MAX_PYRAMID_PER_TICK", 1))
PURE_AI_PYRAMID_COOLDOWN_SECONDS = int(_env_float("NEXUS_PURE_AI_PYRAMID_COOLDOWN_SECONDS", 120))
PURE_AI_RESPECT_LEARNING = _env_bool("NEXUS_PURE_AI_RESPECT_LEARNING", True)
PURE_AI_POST_LOSS_COOLDOWN_MINUTES = int(_env_float("NEXUS_PURE_AI_POST_LOSS_COOLDOWN_MINUTES", 45))
PURE_AI_UNIVERSE_MAX_SYMBOLS = int(_env_float("NEXUS_PURE_AI_UNIVERSE_MAX_SYMBOLS", 20))
# Prefer liquid testnet symbols when radar fallback fires (avoids illiquid scan noise).
PURE_AI_PREFERRED_SYMBOLS = tuple(
    s.strip().upper()
    for s in (
        os.getenv(
            "NEXUS_PURE_AI_PREFERRED_SYMBOLS",
            # Default includes core fleets first: BTC/ETH/SOL/PEPE.
            "BTCUSDT,ETHUSDT,SOLUSDT,1000PEPEUSDT,BNBUSDT,XRPUSDT,DOGEUSDT,AVAXUSDT,LINKUSDT",
        )
        or ""
    ).split(",")
    if s.strip()
)


def pure_ai_active() -> bool:
    # Read env dynamically so tests can toggle after module import.
    return bool(_env_bool("NEXUS_PURE_AI_MODE", False))


def pure_ai_bypass_validation() -> bool:
    return pure_ai_active() and PURE_AI_BYPASS_VALIDATION and sandbox_active()


def pure_ai_bypass_fee_churn() -> bool:
    return pure_ai_active() and PURE_AI_BYPASS_FEE_CHURN and sandbox_active()


def pure_ai_bypass_growth_blocks() -> bool:
    return pure_ai_active() and PURE_AI_BYPASS_GROWTH_BLOCKS and sandbox_active()


def pure_ai_bypass_meeting_blocks() -> bool:
    return pure_ai_active() and sandbox_active()


def pure_ai_bypass_radar_cooldown() -> bool:
    return pure_ai_active() and PURE_AI_BYPASS_RADAR_COOLDOWN and sandbox_active()


def pure_ai_respect_learning() -> bool:
    return pure_ai_active() and PURE_AI_RESPECT_LEARNING


def pure_ai_llm_refresh_seconds() -> int:
    if not pure_ai_active() or not PURE_AI_FAST_SCAN:
        return 0
    return max(2, int(PURE_AI_LLM_REFRESH_SECONDS))
