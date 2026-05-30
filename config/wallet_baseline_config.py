"""Wallet baselines and live-vs-fallback sizing for testnet / mainnet."""

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
        return default


# User-declared testnet starting balances (fallback until Binance sync succeeds).
SPOT_BASELINE_CAPITAL = _env_float("NEXUS_SPOT_BASELINE_CAPITAL", 5000.0)
FUTURES_BASELINE_CAPITAL = _env_float("NEXUS_FUTURES_BASELINE_CAPITAL", 5000.0)

# Prefer live Binance wallet; use baselines only when REST equity is 0 / unavailable.
USE_LIVE_WALLET_FOR_SIZING = _env_bool("NEXUS_USE_LIVE_WALLET_FOR_SIZING", True)

# Legacy alias: fallback equity when live sync missing (not a floor on live balance).
SIMULATION_EVAL_EQUITY = _env_float(
    "NEXUS_SIMULATION_EVAL_EQUITY",
    FUTURES_BASELINE_CAPITAL,
)
SIMULATION_SIZING_ENABLED = _env_bool("NEXUS_SIMULATION_SIZING", True)
