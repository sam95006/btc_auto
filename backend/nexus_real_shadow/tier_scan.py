"""Tier1/2/3 funnel scanning strategy."""
from __future__ import annotations

from backend.nexus_real_shadow.tiered_scan import TierScanResult, TieredMarketScanner

Tier1BroadScanner = TieredMarketScanner
Tier2QualityScanner = TieredMarketScanner
Tier3DeepScanner = TieredMarketScanner

__all__ = [
    "TierScanResult",
    "TieredMarketScanner",
    "Tier1BroadScanner",
    "Tier2QualityScanner",
    "Tier3DeepScanner",
]
