"""Cross-lane adapters for V16-D Strategy Expert Router (C regime + G abstention)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from backend.nexus_strategy_expert_router.constants import REGIME_PROB_KEYS
from backend.nexus_strategy_expert_router.models import MarketContext, RegimeProbabilities


def regime_probabilities_from_engine(engine_out: dict[str, Any]) -> RegimeProbabilities:
    """Bind V16-C engine output → router RegimeProbabilities (fail-closed on unsafe)."""
    probs = engine_out.get("probabilities") if isinstance(engine_out.get("probabilities"), dict) else {}
    formal = str(engine_out.get("formal_state") or "UNKNOWN").upper()
    trading_unsafe = bool(engine_out.get("trading_unsafe")) or formal in {"UNKNOWN", "MIXED"}
    conf = float(probs.get("regime_confidence", engine_out.get("regime_confidence", 0.0)) or 0.0)
    if trading_unsafe or conf < 0.25 or engine_out.get("fail_closed"):
        # Mirror C UNKNOWN packaging: zero directional/stress entry signals.
        return RegimeProbabilities(
            regime_confidence=0.0 if formal == "UNKNOWN" else conf,
            regime_freshness=float(
                probs.get("regime_freshness", engine_out.get("regime_freshness", 0.0)) or 0.0
            ),
        )
    kwargs = {k: float(probs.get(k, 0.0) or 0.0) for k in REGIME_PROB_KEYS}
    kwargs["regime_confidence"] = conf
    kwargs["regime_freshness"] = float(probs.get("regime_freshness", 0.0) or 0.0)
    return RegimeProbabilities(**kwargs)


def bind_regime_engine_to_context(
    ctx: MarketContext,
    engine_out: dict[str, Any],
) -> MarketContext:
    """Attach V16-C formal_state / trading_unsafe onto an existing MarketContext."""
    formal = str(engine_out.get("formal_state") or "UNKNOWN").upper()
    trading_unsafe = bool(engine_out.get("trading_unsafe")) or formal in {"UNKNOWN", "MIXED"}
    return replace(
        ctx,
        regime=regime_probabilities_from_engine(engine_out),
        regime_formal_state=formal,
        trading_unsafe=trading_unsafe,
    )


def apply_abstention_verdict(
    ctx: MarketContext,
    abstention: dict[str, Any] | str,
) -> MarketContext:
    """Bind V16-G abstention verdict onto MarketContext (fail-closed)."""
    if isinstance(abstention, str):
        verdict = abstention.strip().upper()
        uncertainty = ctx.uncertainty
        execution_allowed = verdict in {"ALLOW", "ALLOW_REDUCED"}
    else:
        verdict = str(abstention.get("verdict") or "BLOCK").strip().upper()
        uncertainty = max(
            float(ctx.uncertainty),
            float(abstention.get("uncertainty_score") or 0.0),
        )
        execution_allowed = bool(abstention.get("execution_allowed", verdict in {"ALLOW", "ALLOW_REDUCED"}))
    forced = ctx.lesson_forced_abstain or verdict in {"ABSTAIN", "BLOCK"}
    risk_allow = ctx.risk_gate_allow and execution_allowed and verdict not in {"BLOCK"}
    reason = ctx.risk_gate_reason
    if verdict in {"WAIT", "ABSTAIN", "BLOCK"}:
        reason = f"ABSTENTION_{verdict}"
    return replace(
        ctx,
        abstention_verdict=verdict,
        uncertainty=uncertainty,
        lesson_forced_abstain=forced,
        risk_gate_allow=risk_allow,
        risk_gate_reason=reason,
    )
