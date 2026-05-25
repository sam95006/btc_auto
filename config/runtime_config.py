import os


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def always_on_trading_enabled() -> bool:
    """24/7 mode: keep worker trading; major news alerts without auto-pause."""
    return _env_bool("NEXUS_ALWAYS_ON_TRADING", False)


def tick_seconds() -> float:
    return max(1.0, float(os.getenv("NEXUS_RUNTIME_TICK_SECONDS", "2") or "2"))
