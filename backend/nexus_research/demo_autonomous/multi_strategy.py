"""Multi-strategy scorer for Long/Short autonomous Demo candidates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.nexus_research.demo_strategy.market_features import MarketFeatures


STRATEGIES = (
    "TREND_FOLLOWING",
    "BREAKOUT",
    "PULLBACK",
    "MOMENTUM",
    "MEAN_REVERSION",
    "VOL_EXPANSION",
    "FUNDING_OI_DIVERGENCE",
    "ORDER_FLOW",
)

REGIMES = (
    "BULL_TREND",
    "BEAR_TREND",
    "RANGE",
    "BREAKOUT",
    "HIGH_VOLATILITY",
    "LOW_LIQUIDITY",
    "EVENT_RISK",
    "UNCERTAIN",
)


@dataclass
class StrategyScore:
    strategy: str
    score: float
    regime_fit: bool
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "score": self.score,
            "regimeFit": self.regime_fit,
            "notes": self.notes,
        }


def infer_regime(features: MarketFeatures) -> str:
    atr = float(features.atr_pct or 0.0)
    spread = float(features.spread_bps or 0.0)
    trend = float(features.trend_score or 0.0)
    if spread >= 35 or (features.volume_24h_usd or 0) < 1e6:
        return "LOW_LIQUIDITY"
    if atr >= 6.0:
        return "HIGH_VOLATILITY"
    if abs(trend) >= 40 and atr >= 2.5:
        return "BREAKOUT" if abs(float(features.momentum_score or 0)) >= 35 else (
            "BULL_TREND" if trend > 0 else "BEAR_TREND"
        )
    if abs(trend) >= 25:
        return "BULL_TREND" if trend > 0 else "BEAR_TREND"
    if atr < 1.2:
        return "RANGE"
    return "UNCERTAIN"


def _fit(regime: str, strategy: str) -> bool:
    banned = {
        "LOW_LIQUIDITY": set(STRATEGIES),
        "EVENT_RISK": set(STRATEGIES),
        "UNCERTAIN": {"BREAKOUT", "VOL_EXPANSION"},
        "RANGE": {"TREND_FOLLOWING", "BREAKOUT"},
        "HIGH_VOLATILITY": {"MEAN_REVERSION"},
        "BULL_TREND": {"MEAN_REVERSION"},
        "BEAR_TREND": {"MEAN_REVERSION"},
    }
    return strategy not in banned.get(regime, set())


def score_strategies(features: MarketFeatures, direction: str) -> list[StrategyScore]:
    regime = infer_regime(features)
    trend = float(features.trend_score or 0.0)
    mom = float(features.momentum_score or 0.0)
    rsi = float(features.rsi_14 if features.rsi_14 is not None else 50.0)
    atr = float(features.atr_pct or 0.0)
    funding = float(features.funding_rate_8h_pct or 0.0)
    if direction == "SHORT":
        trend, mom = -trend, -mom

    raw: dict[str, float] = {
        "TREND_FOLLOWING": max(0.0, trend),
        "BREAKOUT": max(0.0, (abs(mom) + atr * 8) / 2),
        "PULLBACK": max(0.0, trend * 0.6 + (20 - abs(rsi - 50))),
        "MOMENTUM": max(0.0, mom),
        "MEAN_REVERSION": max(0.0, 40 - abs(trend) + (abs(rsi - 50))),
        "VOL_EXPANSION": max(0.0, atr * 12),
        "FUNDING_OI_DIVERGENCE": max(0.0, 30 - abs(funding) * 1000 + (10 if funding * trend < 0 else 0)),
        "ORDER_FLOW": max(0.0, (mom + trend) / 2),
    }
    out: list[StrategyScore] = []
    for name, score in raw.items():
        fit = _fit(regime, name)
        out.append(StrategyScore(name, score if fit else score * 0.25, fit, notes=regime))
    out.sort(key=lambda s: (s.regime_fit, s.score), reverse=True)
    return out


def pick_best_strategy(features: MarketFeatures, direction: str) -> tuple[str, str, float]:
    scores = score_strategies(features, direction)
    regime = infer_regime(features)
    best = next((s for s in scores if s.regime_fit), scores[0] if scores else None)
    if best is None:
        return "TREND_FOLLOWING", regime, 0.0
    return best.strategy, regime, best.score
