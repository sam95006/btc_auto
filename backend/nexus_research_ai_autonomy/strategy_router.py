"""Strategy Router — map 9 implemented families to regimes; no invented strategies."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_research_ai_autonomy.constants import IMPLEMENTED_STRATEGY_FAMILIES

# Compatible regimes per implemented family (defensible mapping only).
FAMILY_REGIME_MAP: dict[str, frozenset[str]] = {
    "TREND": frozenset({"TREND_UP", "TREND_DOWN"}),
    "BREAKOUT": frozenset({"BREAKOUT", "HIGH_VOLATILITY", "TREND_UP", "TREND_DOWN"}),
    "MOMENTUM": frozenset({"TREND_UP", "TREND_DOWN", "BREAKOUT", "HIGH_VOLATILITY"}),
    "MEAN_REVERSION": frozenset({"RANGE", "LOW_VOLATILITY"}),
    "REVERSAL": frozenset({"CROWDING", "RANGE", "TREND_UP", "TREND_DOWN"}),
    "STRUCTURE": frozenset({"RANGE", "TREND_UP", "TREND_DOWN", "BREAKOUT"}),
    "VOLATILITY": frozenset({"HIGH_VOLATILITY", "LOW_VOLATILITY", "BREAKOUT"}),
    "DERIVATIVES": frozenset({"CROWDING", "TREND_UP", "TREND_DOWN", "HIGH_VOLATILITY"}),
    "CROSS_SECTIONAL": frozenset({"TREND_UP", "TREND_DOWN", "RANGE", "HIGH_VOLATILITY"}),
}

REGIME_PREFERRED_FAMILIES: dict[str, list[str]] = {
    "TREND_UP": ["TREND", "MOMENTUM", "STRUCTURE"],
    "TREND_DOWN": ["TREND", "MOMENTUM", "STRUCTURE"],
    "RANGE": ["MEAN_REVERSION", "STRUCTURE", "REVERSAL"],
    "BREAKOUT": ["BREAKOUT", "MOMENTUM", "VOLATILITY"],
    "HIGH_VOLATILITY": ["VOLATILITY", "BREAKOUT", "MOMENTUM"],
    "LOW_VOLATILITY": ["MEAN_REVERSION", "STRUCTURE"],
    "CROWDING": ["DERIVATIVES", "REVERSAL"],
    "LIQUIDITY_STRESS": [],  # abstain — no invented stress-arb family
    "UNCERTAIN": [],
}


@dataclass
class StrategyRouteResult:
    selected_strategy_family: str | None
    strategy_version: str
    strategy_fit_score: float | None
    alternative_strategy: str | None = None
    abstain_reason: str | None = None
    compatible_families: list[str] = field(default_factory=list)
    regime: str = "UNCERTAIN"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResearchStrategyRouter:
    """Decide WHAT TYPE OF TRADE FITS before which coin."""

    def __init__(self, *, strategy_version: str = "v18_2_17_impl9") -> None:
        self.strategy_version = strategy_version
        missing = [f for f in IMPLEMENTED_STRATEGY_FAMILIES if f not in FAMILY_REGIME_MAP]
        if missing:
            raise RuntimeError(f"family_map_incomplete:{missing}")

    def route(self, regime: str, *, preferred: str | None = None) -> StrategyRouteResult:
        regime_u = str(regime or "UNCERTAIN").upper()
        preferred_list = list(REGIME_PREFERRED_FAMILIES.get(regime_u, []))
        compatible = [
            f
            for f in IMPLEMENTED_STRATEGY_FAMILIES
            if regime_u in FAMILY_REGIME_MAP.get(f, frozenset())
        ]

        if regime_u == "UNCERTAIN" or not preferred_list:
            return StrategyRouteResult(
                selected_strategy_family=None,
                strategy_version=self.strategy_version,
                strategy_fit_score=None,
                alternative_strategy=None,
                abstain_reason="regime_uncertain_or_no_compatible_family"
                if regime_u == "UNCERTAIN"
                else "no_implemented_family_for_regime",
                compatible_families=compatible,
                regime=regime_u,
            )

        selected = None
        if preferred and preferred.upper() in preferred_list:
            selected = preferred.upper()
        else:
            selected = preferred_list[0]

        if selected not in IMPLEMENTED_STRATEGY_FAMILIES:
            return StrategyRouteResult(
                selected_strategy_family=None,
                strategy_version=self.strategy_version,
                strategy_fit_score=None,
                abstain_reason=f"family_not_implemented:{selected}",
                compatible_families=compatible,
                regime=regime_u,
            )

        alt = preferred_list[1] if len(preferred_list) > 1 else (compatible[1] if len(compatible) > 1 else None)
        fit = 0.85 if selected in preferred_list[:1] else 0.65
        if selected in preferred_list[1:]:
            fit = 0.7
        return StrategyRouteResult(
            selected_strategy_family=selected,
            strategy_version=self.strategy_version,
            strategy_fit_score=fit,
            alternative_strategy=alt,
            abstain_reason=None,
            compatible_families=compatible,
            regime=regime_u,
        )

    def families(self) -> list[str]:
        return list(IMPLEMENTED_STRATEGY_FAMILIES)
