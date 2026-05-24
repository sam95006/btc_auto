import os


def _float(name, default):
    return float(os.getenv(name, str(default)))


def _int(name, default):
    return int(float(os.getenv(name, str(default))))


def _truthy(name, default=True):
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


# Binance REST refresh (API / WS path)
EXCHANGE_REFRESH_MIN_SECONDS = max(1.0, _float("NEXUS_EXCHANGE_REFRESH_MIN_SECONDS", 2))

# Global RSS / macro news fetch
NEWS_REFRESH_SECONDS = max(30, _int("NEXUS_NEWS_REFRESH_SECONDS", 60))

# WebSocket push cadence
WS_PUSH_INTERVAL_SECONDS = max(0.5, _float("NEXUS_WS_PUSH_INTERVAL_SECONDS", 1))

# Macro indices (Yahoo / Stooq) — avoid hammering on every tick
GLOBAL_INDEX_REFRESH_SECONDS = max(15, _int("NEXUS_GLOBAL_INDEX_REFRESH_SECONDS", 30))

# Optional RADAR whale scan during live refresh (still respects scan cache)
LIVE_REFRESH_RADAR = _truthy("NEXUS_LIVE_REFRESH_RADAR", True)
