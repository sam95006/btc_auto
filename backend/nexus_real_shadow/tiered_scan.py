"""Tiered market scan funnel — Tier1 broad, Tier2 quality, Tier3 deep."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TierScanResult:
    tier1_symbols: list[str] = field(default_factory=list)
    tier2_symbols: list[str] = field(default_factory=list)
    tier3_symbols: list[str] = field(default_factory=list)
    tier1_count: int = 0
    tier2_count: int = 0
    tier3_count: int = 0
    excluded_reasons: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier1_count": self.tier1_count,
            "tier2_count": self.tier2_count,
            "tier3_count": self.tier3_count,
            "tier1_symbols": self.tier1_symbols,
            "tier2_symbols": self.tier2_symbols,
            "tier3_symbols": self.tier3_symbols,
            "excluded_reasons": dict(self.excluded_reasons),
        }


class TieredMarketScanner:
    """Three-tier funnel over discovered instruments + market quality hints."""

    TIER1_MIN_TURNOVER = 10_000_000.0
    TIER2_MIN_LIQUIDITY = 60.0
    TIER3_MIN_MOMENTUM = 0.05

    def scan(
        self,
        instruments: list[dict[str, Any]],
        market_by_symbol: dict[str, dict[str, Any]],
    ) -> TierScanResult:
        result = TierScanResult()
        for inst in instruments:
            sym = str(inst.get("symbol") or "")
            if not sym:
                continue
            md = market_by_symbol.get(sym) or {}
            turnover = _num(md.get("turnover_24h"))
            if turnover is None:
                result.excluded_reasons["MISSING_TURNOVER"] = result.excluded_reasons.get("MISSING_TURNOVER", 0) + 1
                continue
            if turnover < self.TIER1_MIN_TURNOVER:
                result.excluded_reasons["LOW_TURNOVER"] = result.excluded_reasons.get("LOW_TURNOVER", 0) + 1
                continue
            result.tier1_symbols.append(sym)

            liq = _num(md.get("liquidity_score"))
            if liq is None or liq < self.TIER2_MIN_LIQUIDITY:
                result.excluded_reasons["LOW_LIQUIDITY"] = result.excluded_reasons.get("LOW_LIQUIDITY", 0) + 1
                continue
            result.tier2_symbols.append(sym)

            mom = _num(md.get("momentum"))
            if mom is None or abs(mom) < self.TIER3_MIN_MOMENTUM:
                result.excluded_reasons["LOW_MOMENTUM"] = result.excluded_reasons.get("LOW_MOMENTUM", 0) + 1
                continue
            result.tier3_symbols.append(sym)

        result.tier1_count = len(result.tier1_symbols)
        result.tier2_count = len(result.tier2_symbols)
        result.tier3_count = len(result.tier3_symbols)
        return result


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
