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
PURE_AI_TARGET_NOTIONAL_USD = _env_float("NEXUS_PURE_AI_TARGET_NOTIONAL_USD", 1200.0)
PURE_AI_DEFAULT_LEVERAGE = _env_float("NEXUS_PURE_AI_DEFAULT_LEVERAGE", 25.0)
PURE_AI_MAX_PROPOSALS_PER_TICK = int(_env_float("NEXUS_PURE_AI_MAX_PROPOSALS", 4))
PURE_AI_MIN_CONFIDENCE = _env_float("NEXUS_PURE_AI_MIN_CONFIDENCE", 0.22)
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


def pure_ai_active() -> bool:
    # Read env dynamically so tests can toggle after module import.
    return bool(_env_bool("NEXUS_PURE_AI_MODE", False))


def pure_ai_bypass_validation() -> bool:
    return pure_ai_active() and PURE_AI_BYPASS_VALIDATION and sandbox_active()


def pure_ai_bypass_fee_churn() -> bool:
    return pure_ai_active() and PURE_AI_BYPASS_FEE_CHURN and sandbox_active()


def pure_ai_bypass_growth_blocks() -> bool:
    return pure_ai_active() and PURE_AI_BYPASS_GROWTH_BLOCKS and sandbox_active()
