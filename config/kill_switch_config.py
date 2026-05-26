import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return float(default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except Exception:
        return int(default)


KILL_SWITCH_ENABLED = _env_bool("NEXUS_KILL_SWITCH_V2", True)
KILL_SWITCH_SYNC_STALE_SEC = _env_int("NEXUS_KILL_SWITCH_SYNC_STALE_SEC", 180)
KILL_SWITCH_MAX_CONSECUTIVE_LOSSES = _env_int("NEXUS_KILL_SWITCH_MAX_CONSECUTIVE_LOSSES", 5)
KILL_SWITCH_VALIDATION_BLOCK_RATE = _env_float("NEXUS_KILL_SWITCH_VALIDATION_BLOCK_RATE", 0.88)
KILL_SWITCH_AUTO_FLATTEN = _env_bool("NEXUS_KILL_SWITCH_AUTO_FLATTEN", False)
