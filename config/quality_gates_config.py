import os


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return float(default)
    try:
        return float(str(raw).strip())
    except Exception:
        return float(default)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


# Aspirational targets — used to tighten gates when recent performance is weak (not a profit guarantee).
TARGET_WIN_RATE = _env_float("NEXUS_TARGET_WIN_RATE", 0.65)
MIN_TRADE_CONFIDENCE = _env_float("NEXUS_MIN_TRADE_CONFIDENCE", 0.68)
QUALITY_GATE_ENABLED = _env_bool("NEXUS_QUALITY_GATE_ENABLED", True)
WALK_FORWARD_MIN_WIN_RATE = _env_float("NEXUS_WALK_FORWARD_MIN_WIN_RATE", 0.45)
