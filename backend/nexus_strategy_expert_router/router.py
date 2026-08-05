"""Core Strategy Expert Router — select/weight experts into first-class decisions."""
from __future__ import annotations

from typing import Any

from backend.nexus_strategy_expert_router.champion_challenger import (
    RouterPolicySnapshot,
    default_champion,
    default_challenger,
)
from backend.nexus_strategy_expert_router.constants import (
    CHAMPION_ROLE,
    DEFENSIVE_EXPERT,
    FIXED_LEVERAGE,
    NO_TRADE_SIDES,
)
from backend.nexus_strategy_expert_router.cooldown import CooldownBook
from backend.nexus_strategy_expert_router.experts import EXPERT_SPECS
from backend.nexus_strategy_expert_router.formal_params import FormalParamLock
from backend.nexus_strategy_expert_router.hard_bans import HardBanViolation
from backend.nexus_strategy_expert_router.models import (
    MarketContext,
    ReasonTrace,
    RoutingDecision,
)
from backend.nexus_strategy_expert_router.safety_gates import (
    assert_safety_invariants,
    honor_risk_gate,
    resolve_leverage,
)
from backend.nexus_strategy_expert_router.scoring import score_all_experts


def _choose_side(ctx: MarketContext, expert_id: str) -> str:
    spec = EXPERT_SPECS[expert_id]
    if expert_id == DEFENSIVE_EXPERT or not spec.entry_capable:
        if ctx.open_position_side:
            return "REDUCE"
        if ctx.lesson_forced_abstain or ctx.uncertainty >= 0.85 or ctx.data_trust < 0.35:
            return "ABSTAIN"
        return "WAIT"

    if not ctx.risk_gate_allow:
        return "ABSTAIN" if not ctx.open_position_side else "REDUCE"

    if expert_id == "EVENT":
        return "REDUCE" if ctx.open_position_side else "WAIT"

    bull = ctx.regime.strong_bull_probability
    bear = ctx.regime.strong_bear_probability
    if expert_id == "MEAN_REVERSION":
        # Fade crowding / extension.
        if ctx.regime.long_crowding_probability > 0.55 and bull > bear:
            return "SHORT"
        if bear > bull and ctx.regime.long_crowding_probability < 0.35:
            return "LONG"
        return "WAIT"

    if bull >= bear and bull >= 0.45:
        return "LONG"
    if bear > bull and bear >= 0.45:
        return "SHORT"
    if "WAIT" in spec.preferred_sides:
        return "WAIT"
    return "ABSTAIN"


class StrategyExpertRouter:
    """Deterministic expert router with full reason traces and safety gates."""

    def __init__(
        self,
        *,
        cooldown: CooldownBook | None = None,
        formal_lock: FormalParamLock | None = None,
        champion: RouterPolicySnapshot | None = None,
        challenger: RouterPolicySnapshot | None = None,
    ) -> None:
        self.cooldown = cooldown or CooldownBook()
        self.formal_lock = formal_lock or FormalParamLock()
        self.champion = champion or default_champion()
        self.challenger = challenger or default_challenger()

    def route(
        self,
        ctx: MarketContext,
        *,
        ai_override_risk_gate: dict[str, Any] | None = None,
        ai_attempt_set_leverage: bool = False,
        force_expert: str | None = None,
    ) -> RoutingDecision:
        trace = ReasonTrace()
        trace.add(
            "ingest_context",
            "accepted market context",
            symbol=ctx.symbol,
            ts_ms=ctx.ts_ms,
            data_trust=ctx.data_trust,
            uncertainty=ctx.uncertainty,
        )

        gate = honor_risk_gate(
            risk_gate_allow=ctx.risk_gate_allow,
            risk_gate_reason=ctx.risk_gate_reason,
            ai_override_attempt=ai_override_risk_gate,
        )
        trace.add(
            "risk_gate",
            "risk gate honored; AI override refused if attempted",
            **{k: gate[k] for k in gate if k != "refusal"},
            refusal=gate.get("refusal"),
        )

        lev = resolve_leverage(
            requested_leverage=ctx.requested_leverage,
            ai_attempt_set_leverage=ai_attempt_set_leverage,
        )
        trace.add(
            "leverage_gate",
            "fixed leverage enforced; AI cannot set leverage",
            leverage=lev["leverage"],
            ai_set_leverage_attempted=lev["ai_set_leverage_attempted"],
            ai_set_leverage_applied=lev["ai_set_leverage_applied"],
        )

        # Effective context respects Risk Gate (never flipped by AI).
        effective_ctx = ctx
        if not gate["effective_allow"] and ctx.risk_gate_allow:
            # Should not happen; fail closed.
            raise HardBanViolation("no_ai_override_risk_gate:inconsistent_effective_allow")

        scores = score_all_experts(effective_ctx)
        trace.add(
            "score_experts",
            "scored all strategy experts",
            count=len(scores),
            factors=[
                "regime_probs",
                "data_trust",
                "execution_cost",
                "liquidity",
                "historical_stability",
                "uncertainty",
                "portfolio_exposure",
                "lesson_restrictions",
            ],
        )

        adjusted: list[tuple[float, object]] = []
        for sc in scores:
            pen = self.cooldown.apply_score_penalty(
                sc.expert_id, sc.adjusted_score, ctx.ts_ms
            )
            # Champion soft weight (shadow) — never force live promotion.
            w = float(self.champion.expert_weights.get(sc.expert_id, 1.0))
            pen *= w
            cooling = self.cooldown.is_cooling(sc.expert_id, ctx.ts_ms)
            degraded = self.cooldown.is_degraded(sc.expert_id)
            if cooling or degraded:
                sc.block_reasons = list(sc.block_reasons)
                if cooling:
                    sc.block_reasons.append("cooldown_active")
                if degraded:
                    sc.block_reasons.append("degraded")
            sc.adjusted_score = pen
            # Eligibility: cooldown/degrade blocks entry experts only.
            if sc.expert_id != DEFENSIVE_EXPERT and (cooling or degraded):
                sc.eligible = False
            adjusted.append((pen, sc))

        adjusted.sort(key=lambda t: t[0], reverse=True)
        ranked = [s for _, s in adjusted]
        trace.add(
            "rank_experts",
            "ranked experts after cooldown/degradation/champion weights",
            ranking=[
                {"expert_id": s.expert_id, "score": s.adjusted_score, "eligible": s.eligible}
                for s in ranked[:5]
            ],
        )

        winner = None
        if force_expert:
            for s in ranked:
                if s.expert_id == force_expert:
                    winner = s
                    break
            if winner is None:
                raise ValueError(f"force_expert not found: {force_expert}")
            trace.add("force_expert", "forced expert for fixture probe", expert_id=force_expert)
        else:
            # Prefer highest eligible; DEFENSIVE always eligible and may win.
            for s in ranked:
                if s.eligible or s.expert_id == DEFENSIVE_EXPERT:
                    winner = s
                    break
            if winner is None:
                winner = next(s for s in ranked if s.expert_id == DEFENSIVE_EXPERT)

        # If top non-defensive is ineligible, defensive can still outscore and win.
        if (
            winner.expert_id != DEFENSIVE_EXPERT
            and not winner.eligible
        ):
            defensive = next(s for s in ranked if s.expert_id == DEFENSIVE_EXPERT)
            winner = defensive
            trace.add(
                "fallback_defensive",
                "entry expert ineligible; DEFENSIVE_NO_TRADE wins",
                score=defensive.adjusted_score,
            )

        # Hard ban: never force a trade when defensive wins on score.
        top = ranked[0]
        if top.expert_id == DEFENSIVE_EXPERT and force_expert and force_expert != DEFENSIVE_EXPERT:
            # Fixture may force, but production path refuses.
            raise HardBanViolation("no_force_trade_when_defensive_wins")

        side = _choose_side(effective_ctx, winner.expert_id)

        # Risk gate block forces no-trade sides.
        if not gate["effective_allow"] and side in ("LONG", "SHORT"):
            side = "ABSTAIN" if not ctx.open_position_side else "REDUCE"
            trace.add(
                "risk_gate_side_override",
                "blocked risk gate coerced side to no-trade",
                side=side,
            )

        no_trade = side in NO_TRADE_SIDES or winner.expert_id == DEFENSIVE_EXPERT
        if winner.expert_id == DEFENSIVE_EXPERT and side not in NO_TRADE_SIDES:
            # Defensive cannot emit LONG/SHORT.
            side = "ABSTAIN"
            no_trade = True
            trace.add("defensive_side_clamp", "DEFENSIVE_NO_TRADE clamped to ABSTAIN")

        # Challenger = next best different expert (shadow observation).
        challenger_id = None
        for s in ranked:
            if s.expert_id != winner.expert_id:
                challenger_id = s.expert_id
                break

        formal_locked = self.formal_lock.is_locked(ctx.ts_ms)
        cooldown_active = self.cooldown.is_cooling(winner.expert_id, ctx.ts_ms)
        degradation_active = self.cooldown.is_degraded(winner.expert_id)

        self.cooldown.record_selection(winner.expert_id, ctx.ts_ms)

        trace.add(
            "select_winner",
            "selected winning expert and first-class side",
            expert_id=winner.expert_id,
            side=side,
            score=winner.adjusted_score,
            no_trade=no_trade,
            challenger_expert_id=challenger_id,
        )

        decision = RoutingDecision(
            expert_id=winner.expert_id,
            side=side,
            score=float(winner.adjusted_score),
            no_trade=no_trade,
            reason_trace=trace,
            expert_scores=ranked,
            champion_role=CHAMPION_ROLE,
            challenger_expert_id=challenger_id,
            cooldown_active=cooldown_active,
            degradation_active=degradation_active,
            formal_params_locked=formal_locked,
            risk_gate_honored=bool(gate["risk_gate_honored"]),
            leverage_ai_mutation_blocked=bool(lev["leverage_ai_mutation_blocked"]),
            leverage=int(lev["leverage"]),
            ai_override_risk_gate_applied=bool(gate["ai_override_risk_gate_applied"]),
            ai_set_leverage_applied=bool(lev["ai_set_leverage_applied"]),
            metadata={
                "risk_gate": gate,
                "leverage_gate": lev,
                "champion_policy_id": self.champion.policy_id,
                "challenger_policy_id": self.challenger.policy_id,
                "formal_params": self.formal_lock.to_dict(),
                "fixed_leverage": FIXED_LEVERAGE,
            },
        )
        assert_safety_invariants(decision.to_dict())
        if decision.reason_trace.steps == []:
            raise RuntimeError("reason_trace_required")
        return decision
