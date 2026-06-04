"""Hemostasis (止血) guardrails — pause bleeding before full v5 company rollout."""

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


# Defensive Mode: block all new Futures entries; exits (SL/TP/reduce/close) still run.
DEFENSIVE_MODE = _env_bool("NEXUS_DEFENSIVE_MODE", True)

# Radar scan-only: disable radar_dispatch auto-open (radar_market_scan_strategy).
RADAR_AUTO_TRADE_ENABLED = _env_bool("NEXUS_RADAR_AUTO_TRADE", False)

# Fleet anti-burst (Futures).
FLEET_BURST_ENABLED = _env_bool("NEXUS_FLEET_BURST_ENABLED", True)
FLEET_BURST_CONSECUTIVE_PAUSE_3H = float(os.getenv("NEXUS_FLEET_BURST_PAUSE_3H", "1"))
FLEET_BURST_CONSECUTIVE_PAUSE_5H = float(os.getenv("NEXUS_FLEET_BURST_PAUSE_5H", "6"))
FLEET_BURST_WATCH_LOSSES_IN_10 = int(os.getenv("NEXUS_FLEET_BURST_WATCH_LOSSES", "7"))
FLEET_BURST_PAUSED_LOSSES_IN_10 = int(os.getenv("NEXUS_FLEET_BURST_PAUSED_LOSSES", "8"))
FLEET_BURST_ROLLING_WINDOW = int(os.getenv("NEXUS_FLEET_BURST_ROLLING_WINDOW", "10"))

# Unified Confidence Engine minimum score (0–100 scale).
CONFIDENCE_ENGINE_MIN_SCORE = float(os.getenv("NEXUS_CONFIDENCE_ENGINE_MIN_SCORE", "60"))


def defensive_mode_active() -> bool:
    return bool(DEFENSIVE_MODE)


def radar_dispatch_entries_allowed() -> bool:
    return bool(RADAR_AUTO_TRADE_ENABLED) and not defensive_mode_active()


def fleet_burst_enabled() -> bool:
    return bool(FLEET_BURST_ENABLED)
