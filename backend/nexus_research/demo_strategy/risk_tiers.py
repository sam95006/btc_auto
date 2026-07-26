"""Demo strategy — risk tier definitions.

Tiers control the maximum fraction of equity that may be risked per trade.
The first controlled order MUST use VALIDATION tier.

Leverage does NOT decide max loss — Risk Budget does.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

RESEARCH_ONLY: bool = True


class RiskTierName(str, Enum):
    VALIDATION = "VALIDATION"
    BASE = "BASE"
    GROWTH = "GROWTH"
    ACCELERATED = "ACCELERATED"


@dataclass(frozen=True)
class RiskTier:
    name: RiskTierName
    min_risk_pct: float
    max_risk_pct: float
    description: str

    def clamp(self, requested_pct: float) -> float:
        return max(self.min_risk_pct, min(self.max_risk_pct, requested_pct))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name.value,
            "minRiskPct": self.min_risk_pct,
            "maxRiskPct": self.max_risk_pct,
            "description": self.description,
        }


VALIDATION_TIER = RiskTier(
    name=RiskTierName.VALIDATION,
    min_risk_pct=0.25,
    max_risk_pct=0.50,
    description="First controlled order. Maximum 0.5% equity risk.",
)

BASE_TIER = RiskTier(
    name=RiskTierName.BASE,
    min_risk_pct=0.50,
    max_risk_pct=0.75,
    description="Standard tier after validation passes.",
)

GROWTH_TIER = RiskTier(
    name=RiskTierName.GROWTH,
    min_risk_pct=0.75,
    max_risk_pct=1.00,
    description="Elevated tier for proven strategy-symbol pairs.",
)

ACCELERATED_TIER = RiskTier(
    name=RiskTierName.ACCELERATED,
    min_risk_pct=1.00,
    max_risk_pct=1.25,
    description="Maximum tier. Hard-capped at 1.25% equity risk.",
)

RISK_TIERS: dict[RiskTierName, RiskTier] = {
    RiskTierName.VALIDATION: VALIDATION_TIER,
    RiskTierName.BASE: BASE_TIER,
    RiskTierName.GROWTH: GROWTH_TIER,
    RiskTierName.ACCELERATED: ACCELERATED_TIER,
}

TIER_PROGRESSION = [
    RiskTierName.VALIDATION,
    RiskTierName.BASE,
    RiskTierName.GROWTH,
    RiskTierName.ACCELERATED,
]


def get_tier(name: RiskTierName | str) -> RiskTier:
    if isinstance(name, str):
        name = RiskTierName(name)
    return RISK_TIERS[name]


def first_order_tier() -> RiskTier:
    """First controlled order MUST use VALIDATION tier."""
    return VALIDATION_TIER
