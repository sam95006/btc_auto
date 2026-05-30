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
MAX_SYSTEM_MARGIN_USD = _env_float("NEXUS_MAX_SYSTEM_MARGIN_USD", 400.0)
MARGIN_AGGRESSION_MULT = _env_float("NEXUS_MARGIN_AGGRESSION_MULT", 1.0)

# Unified bands: leverage + margin multiplier + deployable-pool share (score 0–1).
CONFIDENCE_SIZING_BANDS = [
    {"min": 0.35, "max": 0.50, "leverage": 3, "margin_mult": 0.50, "deployable_pct": 0.035},
    {"min": 0.50, "max": 0.65, "leverage": 5, "margin_mult": 0.65, "deployable_pct": 0.050},
    {"min": 0.65, "max": 0.75, "leverage": 10, "margin_mult": 0.85, "deployable_pct": 0.065},
    {"min": 0.75, "max": 0.85, "leverage": 20, "margin_mult": 1.05, "deployable_pct": 0.080},
    {"min": 0.85, "max": 0.92, "leverage": 50, "margin_mult": 1.35, "deployable_pct": 0.100},
    {"min": 0.92, "max": 1.01, "leverage": 100, "margin_mult": 1.75, "deployable_pct": 0.120},
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
    "BTC": _env_float("NEXUS_FLEET_MARGIN_CAP_BTC", 400.0),
    "ETH": _env_float("NEXUS_FLEET_MARGIN_CAP_ETH", 300.0),
    "SOL": _env_float("NEXUS_FLEET_MARGIN_CAP_SOL", 250.0),
    "PEPE": _env_float("NEXUS_FLEET_MARGIN_CAP_PEPE", 150.0),
    "RADAR": _env_float("NEXUS_FLEET_MARGIN_CAP_RADAR", 200.0),
}

RISK_EVENT_LEVERAGE_CAP = 3
CONSECUTIVE_LOSS_CAP = 3
PEPE_DEFAULT_MAX_LEVERAGE = 20
