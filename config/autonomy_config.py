import os

from config.growth_mode_config import BOLD_TESTNET_ENABLED


def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


_default_autonomy = 2 if BOLD_TESTNET_ENABLED else 1
_default_shadow = not BOLD_TESTNET_ENABLED

NEXUS_AUTONOMY_LEVEL = int(os.getenv("NEXUS_AUTONOMY_LEVEL", str(_default_autonomy)) or _default_autonomy)
NEXUS_LEARNING_AUTO_APPLY = _env_bool("NEXUS_LEARNING_AUTO_APPLY", BOLD_TESTNET_ENABLED)
NEXUS_LEARNING_AUTO_APPROVE = _env_bool("NEXUS_LEARNING_AUTO_APPROVE", NEXUS_LEARNING_AUTO_APPLY)
NEXUS_SHADOW_MODE = _env_bool("NEXUS_SHADOW_MODE", _default_shadow)
NEXUS_AI_PROPOSAL_MAX_PER_TICK = int(os.getenv("NEXUS_AI_PROPOSAL_MAX_PER_TICK", "3") or "3")
STRATEGY_VERSION_ACTIVE = os.getenv("NEXUS_STRATEGY_VERSION", "v1.0.0-core")
