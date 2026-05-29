import os


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return default


MIN_FUTURES_LEVERAGE = _env_int("NEXUS_MIN_FUTURES_LEVERAGE", 3)
MAX_SYSTEM_LEVERAGE = _env_int("NEXUS_MAX_SYSTEM_LEVERAGE", 100)
MAX_SYSTEM_MARGIN_USD = _env_float("NEXUS_MAX_SYSTEM_MARGIN_USD", 150.0)

# Unified bands: leverage + margin multiplier + deployable-pool share (score 0–1).
CONFIDENCE_SIZING_BANDS = [
    {"min": 0.35, "max": 0.50, "leverage": 3, "margin_mult": 0.45, "deployable_pct": 0.025},
    {"min": 0.50, "max": 0.65, "leverage": 5, "margin_mult": 0.55, "deployable_pct": 0.035},
    {"min": 0.65, "max": 0.75, "leverage": 10, "margin_mult": 0.70, "deployable_pct": 0.045},
    {"min": 0.75, "max": 0.85, "leverage": 20, "margin_mult": 0.90, "deployable_pct": 0.055},
    {"min": 0.85, "max": 0.92, "leverage": 50, "margin_mult": 1.15, "deployable_pct": 0.065},
    {"min": 0.92, "max": 1.01, "leverage": 100, "margin_mult": 1.50, "deployable_pct": 0.080},
]

# Backward-compatible alias for leverage engine.
CONFIDENCE_LEVERAGE_TABLE = CONFIDENCE_SIZING_BANDS

FLEET_LEVERAGE_CAPS = {
    "BTC": 100,
    "ETH": 75,
    "SOL": 50,
    "PEPE": 20,
}

FLEET_MARGIN_CAPS = {
    "BTC": _env_float("NEXUS_FLEET_MARGIN_CAP_BTC", 150.0),
    "ETH": _env_float("NEXUS_FLEET_MARGIN_CAP_ETH", 120.0),
    "SOL": _env_float("NEXUS_FLEET_MARGIN_CAP_SOL", 100.0),
    "PEPE": _env_float("NEXUS_FLEET_MARGIN_CAP_PEPE", 60.0),
    "RADAR": _env_float("NEXUS_FLEET_MARGIN_CAP_RADAR", 80.0),
}

RISK_EVENT_LEVERAGE_CAP = 3
CONSECUTIVE_LOSS_CAP = 3
PEPE_DEFAULT_MAX_LEVERAGE = 20
