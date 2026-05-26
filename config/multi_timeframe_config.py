import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


MULTI_TIMEFRAME_ENABLED = _env_bool("NEXUS_MULTI_TIMEFRAME", True)
MTF_TREND_LOOKBACK_TICKS = int(os.getenv("NEXUS_MTF_TREND_LOOKBACK_TICKS", "30") or "30")
MTF_ENTRY_LOOKBACK_TICKS = int(os.getenv("NEXUS_MTF_ENTRY_LOOKBACK_TICKS", "8") or "8")
