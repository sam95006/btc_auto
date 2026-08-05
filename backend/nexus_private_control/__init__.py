"""NEXUS Founder-private control plane V10.

Founder-only lifecycle controls for private-core work. Never exposes a public
product API, never places Demo/Shadow/exchange orders, and never touches
mainnet or real money.

Allowed modes only:
  HISTORICAL_REPLAY_SIMULATED
  PROVIDER_CALIBRATION
  MICROSTRUCTURE_CAPTURE
"""
from __future__ import annotations

from backend.nexus_private_control.modes import ALLOWED_MODES, ModeRejectedError, validate_mode
from backend.nexus_private_control.plane import (
    ControlPlaneError,
    PrivateControlPlaneV10,
    SCHEMA_ID,
)

__all__ = [
    "ALLOWED_MODES",
    "ControlPlaneError",
    "ModeRejectedError",
    "PrivateControlPlaneV10",
    "SCHEMA_ID",
    "validate_mode",
]
