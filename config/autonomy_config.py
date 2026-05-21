import os


def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


NEXUS_AUTONOMY_LEVEL = int(os.getenv("NEXUS_AUTONOMY_LEVEL", "1") or "1")
NEXUS_LEARNING_AUTO_APPLY = _env_bool("NEXUS_LEARNING_AUTO_APPLY", False)
NEXUS_LEARNING_AUTO_APPROVE = _env_bool("NEXUS_LEARNING_AUTO_APPROVE", NEXUS_LEARNING_AUTO_APPLY)
NEXUS_SHADOW_MODE = _env_bool("NEXUS_SHADOW_MODE", True)
NEXUS_AI_PROPOSAL_MAX_PER_TICK = int(os.getenv("NEXUS_AI_PROPOSAL_MAX_PER_TICK", "3") or "3")
STRATEGY_VERSION_ACTIVE = os.getenv("NEXUS_STRATEGY_VERSION", "v1.0.0-core")
