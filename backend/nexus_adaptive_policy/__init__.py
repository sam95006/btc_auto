"""Wave 3 Adaptive AI Trading Policy — shadow-only learning infrastructure."""
from __future__ import annotations

FIXED_LEVERAGE = 25
TARGET_NET_OOS_WIN_RATE = 0.60
MIN_MARGIN = 20
MAX_MARGIN = 500

SCHEMA_VERSION = "wave3.adaptive_policy.v1"

__all__ = [
    "FIXED_LEVERAGE",
    "TARGET_NET_OOS_WIN_RATE",
    "MIN_MARGIN",
    "MAX_MARGIN",
    "SCHEMA_VERSION",
]
