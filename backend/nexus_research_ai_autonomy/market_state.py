"""Market State Engine — real inputs only; UNCERTAIN is valid."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_research_ai_autonomy.constants import REGIME_TYPES


@dataclass
class MarketStateVector:
    trend: float | None = None
    momentum: float | None = None
    volatility: float | None = None
    breadth: float | None = None
    activity: float | None = None
    volume: float | None = None
    oi: float | None = None
    funding: float | None = None
    liquidations: float | None = None
    liquidity: float | None = None
    spread: float | None = None
    depth: float | None = None
    cross_market_correlation: float | None = None
    cost_estimate: float | None = None
    data_trust: float | None = None
    freshness_sec: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class MarketStateResult:
    regime_primary: str
    regime_alternatives: list[str] = field(default_factory=list)
    regime_confidence: float = 0.0
    regime_evidence: list[str] = field(default_factory=list)
    regime_invalidators: list[str] = field(default_factory=list)
    state_vector: MarketStateVector = field(default_factory=MarketStateVector)
    unsupported_dimensions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime_primary": self.regime_primary,
            "regime_alternatives": list(self.regime_alternatives),
            "regime_confidence": self.regime_confidence,
            "regime_evidence": list(self.regime_evidence),
            "regime_invalidators": list(self.regime_invalidators),
            "state_vector": self.state_vector.to_dict(),
            "unsupported_dimensions": list(self.unsupported_dimensions),
        }


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class MarketStateEngine:
    """Classify market regime from available real inputs; never fabricate."""

    def evaluate(self, inputs: dict[str, Any] | None) -> MarketStateResult:
        raw = dict(inputs or {})
        vec = MarketStateVector(
            trend=_f(raw.get("trend")),
            momentum=_f(raw.get("momentum")),
            volatility=_f(raw.get("volatility")),
            breadth=_f(raw.get("breadth")),
            activity=_f(raw.get("activity")),
            volume=_f(raw.get("volume")),
            oi=_f(raw.get("oi")),
            funding=_f(raw.get("funding")),
            liquidations=_f(raw.get("liquidations")),
            liquidity=_f(raw.get("liquidity")),
            spread=_f(raw.get("spread")),
            depth=_f(raw.get("depth")),
            cross_market_correlation=_f(raw.get("cross_market_correlation")),
            cost_estimate=_f(raw.get("cost_estimate")),
            data_trust=_f(raw.get("data_trust")),
            freshness_sec=_f(raw.get("freshness_sec")),
        )

        unsupported: list[str] = []
        for name in (
            "trend",
            "momentum",
            "volatility",
            "breadth",
            "activity",
            "volume",
            "oi",
            "funding",
            "liquidations",
            "liquidity",
            "spread",
            "depth",
            "cross_market_correlation",
            "cost_estimate",
            "data_trust",
            "freshness_sec",
        ):
            if getattr(vec, name) is None and name not in raw:
                unsupported.append(name)

        evidence: list[str] = []
        invalidators: list[str] = []
        alternatives: list[str] = []

        # Freshness / trust fail-closed toward UNCERTAIN (not fake certainty).
        if vec.freshness_sec is not None and vec.freshness_sec > 120:
            invalidators.append("stale_data")
        if vec.data_trust is not None and vec.data_trust < 0.4:
            invalidators.append("low_data_trust")

        if invalidators or (vec.trend is None and vec.momentum is None and vec.volatility is None):
            return MarketStateResult(
                regime_primary="UNCERTAIN",
                regime_alternatives=[],
                regime_confidence=0.0,
                regime_evidence=evidence + ["insufficient_or_untrusted_inputs"],
                regime_invalidators=invalidators,
                state_vector=vec,
                unsupported_dimensions=unsupported,
            )

        scores: dict[str, float] = {r: 0.0 for r in REGIME_TYPES if r != "UNCERTAIN"}

        if vec.trend is not None:
            if vec.trend > 0.35:
                scores["TREND_UP"] += 0.45
                evidence.append("trend_positive")
            elif vec.trend < -0.35:
                scores["TREND_DOWN"] += 0.45
                evidence.append("trend_negative")
            else:
                scores["RANGE"] += 0.25
                evidence.append("trend_flat")

        if vec.momentum is not None:
            if abs(vec.momentum) > 0.4:
                if vec.momentum > 0:
                    scores["TREND_UP"] += 0.2
                    scores["BREAKOUT"] += 0.15
                else:
                    scores["TREND_DOWN"] += 0.2
                    scores["BREAKOUT"] += 0.15
                evidence.append("momentum_elevated")
            else:
                scores["RANGE"] += 0.1

        if vec.volatility is not None:
            if vec.volatility > 0.7:
                scores["HIGH_VOLATILITY"] += 0.4
                scores["BREAKOUT"] += 0.15
                evidence.append("high_volatility")
            elif vec.volatility < 0.25:
                scores["LOW_VOLATILITY"] += 0.4
                scores["RANGE"] += 0.15
                evidence.append("low_volatility")

        if vec.funding is not None and abs(vec.funding) > 0.0003:
            scores["CROWDING"] += 0.35
            evidence.append("funding_crowding")

        if vec.spread is not None and vec.spread > 0.0015:
            scores["LIQUIDITY_STRESS"] += 0.4
            evidence.append("wide_spread")
        if vec.liquidity is not None and vec.liquidity < 0.3:
            scores["LIQUIDITY_STRESS"] += 0.3
            evidence.append("thin_liquidity")

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        primary, primary_score = ranked[0]
        if primary_score < 0.25:
            return MarketStateResult(
                regime_primary="UNCERTAIN",
                regime_alternatives=[r for r, s in ranked[:3] if s > 0],
                regime_confidence=float(primary_score),
                regime_evidence=evidence + ["weak_regime_signal"],
                regime_invalidators=invalidators,
                state_vector=vec,
                unsupported_dimensions=unsupported,
            )

        alternatives = [r for r, s in ranked[1:4] if s >= 0.2]
        confidence = min(0.95, primary_score)
        if primary not in REGIME_TYPES:
            primary = "UNCERTAIN"
        return MarketStateResult(
            regime_primary=primary,
            regime_alternatives=alternatives,
            regime_confidence=confidence,
            regime_evidence=evidence,
            regime_invalidators=invalidators,
            state_vector=vec,
            unsupported_dimensions=unsupported,
        )
