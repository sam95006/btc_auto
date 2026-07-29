"""Wave 5 Real Public Market Shadow Runtime — public data only, no exchange write."""
from __future__ import annotations

PUBLIC_MARKET_DATA_ONLY = True
FIXED_LEVERAGE = 25
MAX_OPEN = 2
MAX_PENDING = 2
MIN_MARGIN = 20
MAX_MARGIN = 500

SCHEMA_VERSION = "wave5.real_public_shadow.v1"

SHADOW_LABELS = frozenset(
    {
        "PUBLIC MARKET DATA",
        "SHADOW SIMULATION",
        "NOT EXECUTED",
        "NO EXCHANGE WRITE",
    }
)

__all__ = [
    "PUBLIC_MARKET_DATA_ONLY",
    "FIXED_LEVERAGE",
    "MAX_OPEN",
    "MAX_PENDING",
    "MIN_MARGIN",
    "MAX_MARGIN",
    "SCHEMA_VERSION",
    "SHADOW_LABELS",
]
