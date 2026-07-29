"""Bybit Demo Execution Validation — independent DEMO-only service boundary."""
from __future__ import annotations

BYBIT_DEMO = True
MAINNET = False
REAL_MONEY = False

FIXED_LEVERAGE = 25
MAX_OPEN = 2
MAX_PENDING = 2
MIN_MARGIN = 20
MAX_MARGIN = 500

DEMO_EXECUTION_LABELS = frozenset(
    {
        "BYBIT_DEMO=true",
        "MAINNET=false",
        "REAL_MONEY=false",
        "DEMO_AUTONOMOUS_DISABLED",
        "FOUNDER_CONFIRMATION_REQUIRED",
    }
)

PACKAGE_PHASE = "bybit-demo-execution-validation"
SERVICE_NAME = "nexus-bybit-demo-learning-validation"

__all__ = [
    "BYBIT_DEMO",
    "DEMO_EXECUTION_LABELS",
    "FIXED_LEVERAGE",
    "MAINNET",
    "MAX_MARGIN",
    "MAX_OPEN",
    "MAX_PENDING",
    "MIN_MARGIN",
    "PACKAGE_PHASE",
    "REAL_MONEY",
    "SERVICE_NAME",
]
