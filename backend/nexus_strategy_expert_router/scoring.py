"""Expert scoring from regime probs and routing factors."""
from __future__ import annotations

from backend.nexus_strategy_expert_router.constants import (
    DEFENSIVE_EXPERT,
    MAX_COST_BPS_FOR_ENTRY,
    MAX_PORTFOLIO_EXPOSURE,
    MAX_UNCERTAINTY_FOR_ENTRY,
    MIN_DATA_TRUST,
    MIN_LIQUIDITY_SCORE,
    ROUTING_FACTORS,
)
from backend.nexus_strategy_expert_router.experts import (
    EXPERT_SPECS,
    assert_expert_catalog_complete,
    regime_affinity,
)
from backend.nexus_strategy_expert_router.models import ExpertScore, MarketContext


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def score_expert(ctx: MarketContext, expert_id: str) -> ExpertScore:
    assert_expert_catalog_complete()
    spec = EXPERT_SPECS[expert_id]
    blocks: list[str] = []
    raw = regime_affinity(spec, ctx.regime)

    data_trust = _clamp01(ctx.data_trust)
    liquidity = _clamp01(ctx.liquidity_score)
    stability = _clamp01(ctx.historical_stability)
    uncertainty = _clamp01(ctx.uncertainty)
    exposure = _clamp01(ctx.portfolio_exposure)
    cost_bps = float(ctx.execution_cost_bps)

    # Factor contributions (documented in reason traces).
    trust_term = data_trust
    cost_term = max(0.0, 1.0 - (cost_bps / max(MAX_COST_BPS_FOR_ENTRY, 1e-9)))
    liq_term = liquidity
    stab_term = stability
    unc_term = 1.0 - uncertainty
    port_term = 1.0 - exposure

    adjusted = raw
    if expert_id != DEFENSIVE_EXPERT:
        # Preserve directional signal under healthy context.
        adjusted *= 0.55 + 0.45 * trust_term
        adjusted *= 1.0 - spec.cost_sensitivity * (1.0 - cost_term) * 0.35
        adjusted *= 1.0 - spec.liquidity_sensitivity * (1.0 - liq_term) * 0.35
        adjusted *= 0.65 + 0.35 * (stab_term ** max(spec.stability_preference, 0.1))
        adjusted *= 1.0 - spec.uncertainty_sensitivity * (1.0 - unc_term) * 0.40
        adjusted *= 0.70 + 0.30 * port_term
    else:
        adjusted *= 0.4 + 0.6 * trust_term
        adjusted *= 0.55 + 0.45 * port_term

    # Defensive floor only under material stress — mild uncertainty must not
    # thrash every calm regime into no-trade.
    if expert_id == DEFENSIVE_EXPERT:
        stress = max(
            ctx.regime.liquidity_stress_probability,
            ctx.regime.event_risk_probability,
            ctx.regime.regime_transition_probability,
            ctx.regime.correlation_breakdown_probability * 0.85,
            uncertainty if uncertainty >= 0.70 else 0.0,
            (1.0 - data_trust) if data_trust <= 0.50 else 0.0,
        )
        if stress >= 0.45:
            adjusted = max(adjusted, 0.55 + 1.35 * stress)
            blocks.append("defensive_stress_floor")
        if ctx.lesson_forced_abstain:
            adjusted = max(adjusted, 2.5)
            blocks.append("lesson_forced_abstain_boost")
        # Soft baseline so defensive remains rankable but loses healthy regimes.
        adjusted = max(adjusted, 0.05)

    eligible = True
    if expert_id in ctx.lesson_blocked_experts:
        eligible = False
        blocks.append("lesson_restriction")
        adjusted = -1e9

    if expert_id != DEFENSIVE_EXPERT and spec.entry_capable:
        if data_trust < MIN_DATA_TRUST:
            eligible = False
            blocks.append("data_trust_below_min")
        if uncertainty > MAX_UNCERTAINTY_FOR_ENTRY:
            eligible = False
            blocks.append("uncertainty_too_high")
        if cost_bps > MAX_COST_BPS_FOR_ENTRY:
            eligible = False
            blocks.append("execution_cost_too_high")
        if liquidity < MIN_LIQUIDITY_SCORE:
            eligible = False
            blocks.append("liquidity_too_low")
        if exposure > MAX_PORTFOLIO_EXPOSURE:
            eligible = False
            blocks.append("portfolio_exposure_too_high")
        if not ctx.risk_gate_allow:
            eligible = False
            blocks.append("risk_gate_block")
        if float(ctx.regime.regime_freshness) < 0.35:
            eligible = False
            blocks.append("regime_stale")

    # Ineligible entry experts keep score for ranking transparency but cannot win entries.
    if not eligible and expert_id != DEFENSIVE_EXPERT:
        adjusted = min(adjusted, -0.5)

    factors = {
        "regime_probs": raw,
        "data_trust": trust_term,
        "execution_cost": cost_term,
        "liquidity": liq_term,
        "historical_stability": stab_term,
        "uncertainty": unc_term,
        "portfolio_exposure": port_term,
        "lesson_restrictions": 0.0 if "lesson_restriction" in blocks else 1.0,
    }
    assert set(ROUTING_FACTORS) == set(factors)

    return ExpertScore(
        expert_id=expert_id,
        raw_affinity=raw,
        adjusted_score=adjusted,
        eligible=eligible if expert_id != DEFENSIVE_EXPERT else True,
        block_reasons=blocks,
        factor_breakdown=factors,
    )


def score_all_experts(ctx: MarketContext) -> list[ExpertScore]:
    return [score_expert(ctx, eid) for eid in EXPERT_SPECS]
