"""Autonomous Bybit Demo trading — package marker.

Hard bounds:
- api-demo.bybit.com only
- Isolated, max 1 position, no averaging / martingale / auto-add-margin
- Session authorization required for any write
- Mainnet / real money impossible
"""
from __future__ import annotations

RESEARCH_ONLY = False  # Demo execution may write when session authorized
DEMO_ONLY = True
MAINNET_ALLOWED = False
REAL_MONEY_ALLOWED = False

__all__ = [
    "RESEARCH_ONLY",
    "DEMO_ONLY",
    "MAINNET_ALLOWED",
    "REAL_MONEY_ALLOWED",
]
