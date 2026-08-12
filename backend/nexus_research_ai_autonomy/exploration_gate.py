"""RESEARCH_EXPLORATION_GATE_V1 — less restrictive than formal; keep safety."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


GATE_ID = "RESEARCH_EXPLORATION_GATE_V1"


@dataclass
class ExplorationGateResult:
    gate_id: str = GATE_ID
    passed: bool = False
    reasons: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    edge_vs_cost: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _f(v: Any, default: float | None = None) -> float | None:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class ResearchExplorationGateV1:
    """Economic/operational gate for RESEARCH_AI_DEMO (not Formal WF/OOS)."""

    def evaluate(self, packet: dict[str, Any] | None) -> ExplorationGateResult:
        p = dict(packet or {})
        reasons: list[str] = []
        blocks: list[str] = []
        scores: dict[str, float] = {}

        # Hard safety — never lower these.
        data_trust = _f(p.get("data_trust"), 0.0) or 0.0
        freshness_sec = _f(p.get("freshness_sec"), 9999.0) or 9999.0
        if data_trust < 0.5:
            blocks.append("data_integrity_safety")
        else:
            reasons.append("data_trust_ok")
            scores["data_trust"] = data_trust
        if freshness_sec > 90:
            blocks.append("freshness_safety")
        else:
            reasons.append("freshness_ok")
            scores["freshness"] = max(0.0, 1.0 - freshness_sec / 90.0)

        if p.get("exchange_ok") is False:
            blocks.append("exchange_safety")
        else:
            reasons.append("exchange_ok")

        if p.get("position_safety_ok") is False:
            blocks.append("position_safety")
        else:
            reasons.append("position_safety_ok")

        if p.get("loss_safety_ok") is False:
            blocks.append("loss_safety")
        else:
            reasons.append("loss_safety_ok")

        regime = str(p.get("regime") or "UNCERTAIN").upper()
        strategy_fit = _f(p.get("strategy_fit_score"))
        if regime == "UNCERTAIN" or strategy_fit is None or strategy_fit < 0.5:
            blocks.append("regime_or_strategy_fit")
        else:
            reasons.append("regime_strategy_fit_ok")
            scores["strategy_fit"] = strategy_fit

        expected_edge = _f(p.get("expected_edge"))
        estimated_cost = _f(p.get("estimated_cost"))
        edge_meta: dict[str, Any] = {
            "expected_edge": expected_edge,
            "estimated_cost": estimated_cost,
        }
        cost_exception = bool(p.get("cost_relationship_test_exception"))
        if expected_edge is not None and estimated_cost is not None:
            edge_meta["edge_minus_cost"] = expected_edge - estimated_cost
            if expected_edge <= estimated_cost and not cost_exception:
                blocks.append("edge_le_cost")
            elif expected_edge <= estimated_cost and cost_exception:
                reasons.append("cost_relationship_test_tagged")
                edge_meta["exception_tagged"] = True
            else:
                reasons.append("edge_exceeds_cost")
                scores["edge_vs_cost"] = (expected_edge - estimated_cost) / max(estimated_cost, 1e-9)
        else:
            # Thinner evidence allowed vs formal, but still need a thesis signal.
            if p.get("economic_thesis"):
                reasons.append("economic_thesis_present_without_numeric_edge")
            else:
                blocks.append("missing_economic_thesis")

        spread = _f(p.get("spread"), 0.0) or 0.0
        liquidity = _f(p.get("liquidity"), 1.0) or 1.0
        if spread > 0.0025:
            blocks.append("spread_too_wide")
        else:
            reasons.append("spread_ok")
        if liquidity < 0.25:
            blocks.append("liquidity_too_thin")
        else:
            reasons.append("liquidity_ok")

        ai_agree = p.get("ai_quant_agreement")
        if ai_agree is False:
            blocks.append("ai_quant_disagreement")
        elif ai_agree is True:
            reasons.append("ai_quant_agreement")
            scores["agreement"] = 1.0

        critic_objections = list(p.get("critic_objections") or [])
        hard_objections = [o for o in critic_objections if str(o).startswith("HARD:")]
        if hard_objections:
            blocks.append("critic_hard_objection")
        else:
            reasons.append("critic_no_hard_objection")

        # Formal gates must NOT appear as blocks.
        for banned in ("pre_wf", "formal_wf", "oos", "trade_eligible_false"):
            if banned in blocks:
                blocks = [b for b in blocks if b != banned]

        # Explicit: TRADE_ELIGIBLE=false is allowed when radar_eligible + research path.
        if p.get("trade_eligible") is False and p.get("radar_eligible") is True:
            reasons.append("radar_eligible_without_trade_eligible_allowed")

        passed = len(blocks) == 0
        return ExplorationGateResult(
            passed=passed,
            reasons=reasons,
            blocks=blocks,
            edge_vs_cost=edge_meta,
            scores=scores,
        )
