import os
from pathlib import Path


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


COMPOUND_REINVEST_ENABLED = _env_bool("NEXUS_COMPOUND_REINVEST", True)
DAILY_POSITIVE_MODE = _env_bool("NEXUS_DAILY_POSITIVE_MODE", True)
LOCK_PROFIT_AFTER_DAILY_TARGET = _env_bool("NEXUS_LOCK_PROFIT_AFTER_DAILY_TARGET", True)
MATURITY_TARGET_SCORE = _env_float("NEXUS_MATURITY_TARGET_SCORE", 90.0)
MEETING_TIMEZONE = str(os.getenv("NEXUS_MEETING_TIMEZONE", "Asia/Taipei") or "Asia/Taipei").strip()


def compound_state_path():
    data_dir = str(os.getenv("NEXUS_DATA_DIR", "") or "").strip()
    if data_dir:
        return Path(data_dir) / "logs" / "growth_daily_state.json"
    root = Path(__file__).resolve().parents[1]
    return root / "logs" / "growth_daily_state.json"
