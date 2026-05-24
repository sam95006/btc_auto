import os


def _env_float(name, default):
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return float(default)


def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


CAPITAL_FLOOR = _env_float("NEXUS_CAPITAL_FLOOR", 11800.0)
GROWTH_TARGET = _env_float("NEXUS_GROWTH_TARGET", 17700.0)
FLOOR_BUFFER_PCT = _env_float("NEXUS_FLOOR_BUFFER_PCT", 0.02)

DAILY_PNL_TARGET_PCT = _env_float("NEXUS_DAILY_PNL_TARGET_PCT", 0.003)
DAILY_MAX_LOSS_PCT = _env_float("NEXUS_DAILY_MAX_LOSS_PCT", 0.015)
DAILY_DEFENSE_QUALITY = _env_float("NEXUS_DAILY_DEFENSE_QUALITY", 0.78)
DAILY_A_PLUS_QUALITY = _env_float("NEXUS_DAILY_A_PLUS_QUALITY", 0.82)

RECOVERY_MIN_QUALITY = _env_float("NEXUS_RECOVERY_MIN_QUALITY", 0.72)
RECOVERY_MAX_LEVERAGE = _env_float("NEXUS_RECOVERY_MAX_LEVERAGE", 12.0)
RECOVERY_MIN_APPROVAL = _env_float("NEXUS_RECOVERY_MIN_APPROVAL", 0.62)
RECOVERY_MIN_WIN_RATE = _env_float("NEXUS_RECOVERY_MIN_WIN_RATE", 0.48)

GROWTH_MIN_QUALITY = _env_float("NEXUS_GROWTH_MIN_QUALITY", 0.66)
GROWTH_MAX_LEVERAGE = _env_float("NEXUS_GROWTH_MAX_LEVERAGE", 28.0)
GROWTH_MIN_APPROVAL = _env_float("NEXUS_GROWTH_MIN_APPROVAL", 0.58)
GROWTH_POSITION_BOOST = _env_float("NEXUS_GROWTH_POSITION_BOOST", 1.15)
GROWTH_MIN_WIN_RATE = _env_float("NEXUS_GROWTH_MIN_WIN_RATE", 0.42)

FLOOR_GUARD_MAX_LEVERAGE = _env_float("NEXUS_FLOOR_GUARD_MAX_LEVERAGE", 10.0)
FLOOR_GUARD_MIN_QUALITY = _env_float("NEXUS_FLOOR_GUARD_MIN_QUALITY", 0.74)

SETUP_MIN_SAMPLE = int(_env_float("NEXUS_SETUP_MIN_SAMPLE", 5))
SETUP_MIN_WIN_RATE = _env_float("NEXUS_SETUP_MIN_WIN_RATE", 0.38)

BOLD_TESTNET_ENABLED = _env_bool("NEXUS_BOLD_TESTNET", True)
BOLD_MIN_QUALITY = _env_float("NEXUS_BOLD_MIN_QUALITY", 0.55)
