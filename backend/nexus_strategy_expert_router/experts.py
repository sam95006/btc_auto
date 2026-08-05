"""Strategy Expert definitions and regime affinity maps."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from backend.nexus_strategy_expert_router.constants import DEFENSIVE_EXPERT, EXPERT_IDS
from backend.nexus_strategy_expert_router.models import RegimeProbabilities


@dataclass(frozen=True)
class ExpertSpec:
    expert_id: str
    description: str
    entry_capable: bool
    preferred_sides: tuple[str, ...]
    # Weights on RegimeProbabilities fields (affinity contributions).
    regime_weights: Mapping[str, float]
    # Soft multipliers on context quality factors (higher = more sensitive).
    cost_sensitivity: float
    liquidity_sensitivity: float
    uncertainty_sensitivity: float
    stability_preference: float


def _specs() -> dict[str, ExpertSpec]:
    return {
        "TREND": ExpertSpec(
            expert_id="TREND",
            description="Directional continuation under strong bull/bear regimes",
            entry_capable=True,
            preferred_sides=("LONG", "SHORT"),
            regime_weights={
                "strong_bull_probability": 1.0,
                "strong_bear_probability": 1.0,
                "regime_transition_probability": -0.6,
                "liquidity_stress_probability": -0.4,
            },
            cost_sensitivity=0.6,
            liquidity_sensitivity=0.5,
            uncertainty_sensitivity=0.7,
            stability_preference=0.7,
        ),
        "MEAN_REVERSION": ExpertSpec(
            expert_id="MEAN_REVERSION",
            description="Fade extensions when trend weak and crowding high",
            entry_capable=True,
            preferred_sides=("LONG", "SHORT"),
            regime_weights={
                "long_crowding_probability": 0.8,
                "strong_bull_probability": -0.5,
                "strong_bear_probability": -0.5,
                "volatility_expansion_probability": -0.4,
            },
            cost_sensitivity=1.0,
            liquidity_sensitivity=0.8,
            uncertainty_sensitivity=0.8,
            stability_preference=0.9,
        ),
        "BREAKOUT": ExpertSpec(
            expert_id="BREAKOUT",
            description="Volatility expansion with directional confirmation",
            entry_capable=True,
            preferred_sides=("LONG", "SHORT"),
            regime_weights={
                "volatility_expansion_probability": 1.0,
                "strong_bull_probability": 0.5,
                "strong_bear_probability": 0.5,
                "liquidity_stress_probability": -0.7,
            },
            cost_sensitivity=0.7,
            liquidity_sensitivity=0.9,
            uncertainty_sensitivity=0.9,
            stability_preference=0.4,
        ),
        "LIQUIDATION": ExpertSpec(
            expert_id="LIQUIDATION",
            description="Liquidity-stress / cascade opportunistic expert",
            entry_capable=True,
            preferred_sides=("LONG", "SHORT", "WAIT"),
            regime_weights={
                "liquidity_stress_probability": 1.2,
                "volatility_expansion_probability": 0.5,
                "event_risk_probability": 0.3,
            },
            cost_sensitivity=0.9,
            liquidity_sensitivity=1.0,
            uncertainty_sensitivity=1.0,
            stability_preference=0.3,
        ),
        "FUNDING": ExpertSpec(
            expert_id="FUNDING",
            description="Funding / crowding carry and squeeze awareness",
            entry_capable=True,
            preferred_sides=("LONG", "SHORT", "WAIT"),
            regime_weights={
                "long_crowding_probability": 1.0,
                "strong_bull_probability": 0.2,
                "strong_bear_probability": 0.2,
            },
            cost_sensitivity=0.5,
            liquidity_sensitivity=0.4,
            uncertainty_sensitivity=0.6,
            stability_preference=0.6,
        ),
        "OPEN_INTEREST": ExpertSpec(
            expert_id="OPEN_INTEREST",
            description="Open-interest confirmation and divergence expert",
            entry_capable=True,
            preferred_sides=("LONG", "SHORT", "WAIT"),
            regime_weights={
                "long_crowding_probability": 0.6,
                "volatility_expansion_probability": 0.4,
                "regime_transition_probability": 0.3,
            },
            cost_sensitivity=0.5,
            liquidity_sensitivity=0.5,
            uncertainty_sensitivity=0.7,
            stability_preference=0.5,
        ),
        "EVENT": ExpertSpec(
            expert_id="EVENT",
            description="Event-risk defensive / reduce bias",
            entry_capable=True,
            preferred_sides=("WAIT", "REDUCE", "ABSTAIN"),
            regime_weights={
                "event_risk_probability": 1.4,
                "regime_transition_probability": 0.5,
            },
            cost_sensitivity=0.3,
            liquidity_sensitivity=0.3,
            uncertainty_sensitivity=0.4,
            stability_preference=0.2,
        ),
        "VOLATILITY": ExpertSpec(
            expert_id="VOLATILITY",
            description="Vol regime specialist — often WAIT under expansion",
            entry_capable=True,
            preferred_sides=("WAIT", "REDUCE", "LONG", "SHORT"),
            regime_weights={
                "volatility_expansion_probability": 1.1,
                "liquidity_stress_probability": 0.4,
            },
            cost_sensitivity=0.8,
            liquidity_sensitivity=0.7,
            uncertainty_sensitivity=0.8,
            stability_preference=0.4,
        ),
        "CROSS_ASSET": ExpertSpec(
            expert_id="CROSS_ASSET",
            description="Correlation breakdown / cross-asset confirmation",
            entry_capable=True,
            preferred_sides=("LONG", "SHORT", "WAIT", "ABSTAIN"),
            regime_weights={
                "correlation_breakdown_probability": 1.2,
                "regime_transition_probability": 0.4,
            },
            cost_sensitivity=0.6,
            liquidity_sensitivity=0.5,
            uncertainty_sensitivity=0.7,
            stability_preference=0.5,
        ),
        DEFENSIVE_EXPERT: ExpertSpec(
            expert_id=DEFENSIVE_EXPERT,
            description="First-class no-trade expert — may win outright",
            entry_capable=False,
            preferred_sides=("WAIT", "ABSTAIN", "REDUCE"),
            regime_weights={
                "liquidity_stress_probability": 0.8,
                "event_risk_probability": 0.8,
                "regime_transition_probability": 0.7,
                "correlation_breakdown_probability": 0.5,
                "volatility_expansion_probability": 0.3,
            },
            cost_sensitivity=0.2,
            liquidity_sensitivity=0.2,
            uncertainty_sensitivity=0.2,
            stability_preference=0.1,
        ),
    }


EXPERT_SPECS: dict[str, ExpertSpec] = _specs()


def assert_expert_catalog_complete() -> None:
    missing = set(EXPERT_IDS) - set(EXPERT_SPECS)
    extra = set(EXPERT_SPECS) - set(EXPERT_IDS)
    if missing or extra:
        raise RuntimeError(f"expert catalog mismatch missing={missing} extra={extra}")


def regime_affinity(spec: ExpertSpec, regime: RegimeProbabilities) -> float:
    """Deterministic affinity in roughly [-2, 3] before context adjustments."""
    total = 0.0
    rd = regime.as_dict()
    for key, weight in spec.regime_weights.items():
        total += float(weight) * float(rd.get(key, 0.0))
    # Confidence / freshness soft gates.
    total *= 0.5 + 0.5 * float(regime.regime_confidence)
    total *= 0.5 + 0.5 * float(regime.regime_freshness)
    return total
