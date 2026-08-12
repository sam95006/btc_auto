"""Allowed operating modes for the Founder-private control plane."""
from __future__ import annotations

from typing import Any

ALLOWED_MODES: frozenset[str] = frozenset(
    {
        "HISTORICAL_REPLAY_SIMULATED",
        "PROVIDER_CALIBRATION",
        "MICROSTRUCTURE_CAPTURE",
    }
)

# Explicitly banned — fail closed even if similar names are used.
BANNED_MODE_FRAGMENTS: tuple[str, ...] = (
    "DEMO",
    "SHADOW",
    "MAINNET",
    "LIVE_TRADING",
    "REAL_MONEY",
    "EXCHANGE_WRITE",
    "OOS",
    "WALK_FORWARD",
    "PUBLIC",
)


class ModeRejectedError(ValueError):
    """Raised when a mode is not in the Founder-allowed set. Fail-closed."""


def validate_mode(mode: str | None) -> str:
    """Return normalized mode or raise ModeRejectedError."""
    if mode is None or not str(mode).strip():
        raise ModeRejectedError("mode_required")
    normalized = str(mode).strip().upper()
    for frag in BANNED_MODE_FRAGMENTS:
        if frag in normalized and normalized not in ALLOWED_MODES:
            raise ModeRejectedError(f"banned_mode_fragment:{frag}:{normalized}")
    if normalized not in ALLOWED_MODES:
        raise ModeRejectedError(f"mode_not_allowed:{normalized}")
    return normalized


def mode_contract() -> dict[str, Any]:
    return {
        "allowed_modes": sorted(ALLOWED_MODES),
        "banned_mode_fragments": list(BANNED_MODE_FRAGMENTS),
        "exchange_writes_permitted": False,
        "demo_orders_permitted": False,
        "shadow_orders_permitted": False,
        "mainnet_permitted": False,
        "real_money_permitted": False,
        "public_api_permitted": False,
    }
