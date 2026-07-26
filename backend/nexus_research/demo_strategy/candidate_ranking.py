"""Demo strategy — candidate ranking.

Ranked list of strategy candidates with per-symbol eligibility,
direction bias, and priority. Used by the strategy evaluator to
decide which candidates to evaluate first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

RESEARCH_ONLY: bool = True


@dataclass(frozen=True)
class StrategyCandidate:
    symbol: str
    direction: str  # LONG | SHORT | BOTH
    priority: int  # lower = higher priority
    min_score: float  # minimum composite score to pass
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "priority": self.priority,
            "minScore": self.min_score,
            "notes": self.notes,
        }


STRATEGY_CANDIDATE_RANKING: list[StrategyCandidate] = [
    StrategyCandidate(
        symbol="BTCUSDT",
        direction="BOTH",
        priority=1,
        min_score=55.0,
        notes="Highest liquidity, tightest spreads, most regime data available.",
    ),
    StrategyCandidate(
        symbol="ETHUSDT",
        direction="BOTH",
        priority=2,
        min_score=58.0,
        notes="Strong liquidity, slightly wider spreads than BTC.",
    ),
    StrategyCandidate(
        symbol="SOLUSDT",
        direction="LONG",
        priority=3,
        min_score=62.0,
        notes="Higher volatility; long-only until short-side data is validated.",
    ),
]


def get_candidates_for_symbol(symbol: str) -> list[StrategyCandidate]:
    return [c for c in STRATEGY_CANDIDATE_RANKING if c.symbol == symbol]


def ranked_symbols() -> list[str]:
    """Return symbols in priority order (lowest priority number first)."""
    return [c.symbol for c in sorted(STRATEGY_CANDIDATE_RANKING, key=lambda c: c.priority)]
