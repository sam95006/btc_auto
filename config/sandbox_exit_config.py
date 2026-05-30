"""Testnet sandbox: absolute USD exits + relaxed fee-churn on exits."""

import os

from config.testnet_sandbox_config import TESTNET_SANDBOX_ENABLED
from config.wallet_baseline_config import SIMULATION_EVAL_EQUITY, SIMULATION_SIZING_ENABLED


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


SANDBOX_ABS_EXIT_ENABLED = _env_bool("NEXUS_SANDBOX_ABS_EXIT", TESTNET_SANDBOX_ENABLED)
SANDBOX_TP_ABS_USD = _env_float("NEXUS_SANDBOX_TP_ABS_USD", 25.0)
SANDBOX_SL_ABS_USD = _env_float("NEXUS_SANDBOX_SL_ABS_USD", 15.0)
SANDBOX_RELAX_EXIT_GUARDS = _env_bool("NEXUS_SANDBOX_RELAX_EXIT_GUARDS", True)
SANDBOX_MIN_PARTIAL_PROFIT_USD = _env_float("NEXUS_SANDBOX_MIN_PARTIAL_PROFIT_USD", 0.35)
SANDBOX_MIN_HOLD_SECONDS = _env_float("NEXUS_SANDBOX_MIN_HOLD_SECONDS", 45.0)
