import os

from config.growth_mode_config import BOLD_TESTNET_ENABLED
from config.revenue_target_config import EXPLORATION_AI_PROPOSALS_PER_TICK, REVENUE_GROWTH_MODE


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


AI_LED_TRADING_ENABLED = _env_bool("NEXUS_AI_LED_TRADING", True)
AI_LED_PRIMARY_MODE = _env_bool("NEXUS_AI_LED_PRIMARY", AI_LED_TRADING_ENABLED)
AI_LED_INCLUDE_CORE_FLEETS = _env_bool("NEXUS_AI_LED_CORE_FLEETS", True)
AI_LED_MIN_CONFIDENCE = float(os.getenv("NEXUS_AI_LED_MIN_CONFIDENCE", "0.45" if BOLD_TESTNET_ENABLED else "0.55") or 0.45)
AI_PROPOSAL_MAX_PER_TICK = int(
    os.getenv(
        "NEXUS_AI_PROPOSAL_MAX_PER_TICK",
        str(EXPLORATION_AI_PROPOSALS_PER_TICK if REVENUE_GROWTH_MODE else 5),
    )
    or 5
)
