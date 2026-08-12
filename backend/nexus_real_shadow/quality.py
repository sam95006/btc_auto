"""Fail-closed market quality evaluation for Wave 5 real public shadow runtime."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.nexus_global_shadow.universe import MarketQualityEvaluator as Wave2QualityEvaluator


@dataclass
class QualityVerdict:
    symbol: str
    eligible: bool
    quality: str
    freshness: str
    completeness: str
    liquidity_score: float | None
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "eligible": self.eligible,
            "quality": self.quality,
            "freshness": self.freshness,
            "completeness": self.completeness,
            "liquidity_score": self.liquidity_score,
            "reasons": list(self.reasons),
        }


class RealMarketQualityEvaluator:
    """Wrap Wave2 evaluator with fail-closed semantics for missing public data."""

    def __init__(self) -> None:
        self._inner = Wave2QualityEvaluator()

    def evaluate(self, symbol: str, raw: dict[str, Any] | None) -> QualityVerdict:
        if not raw:
            return QualityVerdict(
                symbol=symbol,
                eligible=False,
                quality="FAIL",
                freshness="MISSING",
                completeness="MISSING",
                liquidity_score=None,
                reasons=["missing_market_data"],
            )
        snap = self._inner.evaluate(symbol, raw)
        passes, gate_reasons = self._inner.passes_quality_gate(snap)
        reasons: list[str] = []
        if raw.get("last_price") is None:
            reasons.append("missing_last_price")
        if raw.get("turnover_24h") is None:
            reasons.append("missing_turnover")
        if raw.get("freshness") in {None, "MISSING", "UNAVAILABLE"}:
            reasons.append("stale_or_missing_freshness")
        eligible = passes and snap.quality == "PASS" and not reasons
        return QualityVerdict(
            symbol=symbol,
            eligible=eligible,
            quality=snap.quality,
            freshness=snap.freshness,
            completeness=snap.completeness,
            liquidity_score=raw.get("liquidity_score"),
            reasons=reasons or list(gate_reasons),
        )
