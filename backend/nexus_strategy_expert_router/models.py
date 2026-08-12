"""Typed models for V16-D Strategy Expert Router."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_strategy_expert_router.constants import (
    DECISION_SIDES,
    EXPERT_IDS,
    REGIME_PROB_KEYS,
)


@dataclass(frozen=True)
class RegimeProbabilities:
    strong_bull_probability: float = 0.0
    strong_bear_probability: float = 0.0
    volatility_expansion_probability: float = 0.0
    liquidity_stress_probability: float = 0.0
    long_crowding_probability: float = 0.0
    correlation_breakdown_probability: float = 0.0
    event_risk_probability: float = 0.0
    regime_transition_probability: float = 0.0
    regime_confidence: float = 0.0
    regime_freshness: float = 1.0

    def as_dict(self) -> dict[str, float]:
        return {k: float(getattr(self, k)) for k in REGIME_PROB_KEYS} | {
            "regime_confidence": float(self.regime_confidence),
            "regime_freshness": float(self.regime_freshness),
        }


@dataclass(frozen=True)
class MarketContext:
    symbol: str
    ts_ms: int
    regime: RegimeProbabilities
    data_trust: float
    execution_cost_bps: float
    liquidity_score: float
    historical_stability: float
    uncertainty: float
    portfolio_exposure: float
    lesson_blocked_experts: tuple[str, ...] = ()
    lesson_forced_abstain: bool = False
    risk_gate_allow: bool = True
    risk_gate_reason: str = "PASS"
    open_position_side: str | None = None
    requested_leverage: int | None = None
    # Cross-lane bindings (V16-C formal regime + V16-G abstention).
    regime_formal_state: str = "CLEAR"
    trading_unsafe: bool = False
    abstention_verdict: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "ts_ms": self.ts_ms,
            "regime": self.regime.as_dict(),
            "data_trust": self.data_trust,
            "execution_cost_bps": self.execution_cost_bps,
            "liquidity_score": self.liquidity_score,
            "historical_stability": self.historical_stability,
            "uncertainty": self.uncertainty,
            "portfolio_exposure": self.portfolio_exposure,
            "lesson_blocked_experts": list(self.lesson_blocked_experts),
            "lesson_forced_abstain": self.lesson_forced_abstain,
            "risk_gate_allow": self.risk_gate_allow,
            "risk_gate_reason": self.risk_gate_reason,
            "open_position_side": self.open_position_side,
            "requested_leverage": self.requested_leverage,
            "regime_formal_state": self.regime_formal_state,
            "trading_unsafe": self.trading_unsafe,
            "abstention_verdict": self.abstention_verdict,
        }


@dataclass
class ExpertScore:
    expert_id: str
    raw_affinity: float
    adjusted_score: float
    eligible: bool
    block_reasons: list[str] = field(default_factory=list)
    factor_breakdown: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReasonStep:
    step: str
    detail: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"step": self.step, "detail": self.detail, "data": dict(self.data)}


@dataclass
class ReasonTrace:
    steps: list[ReasonStep] = field(default_factory=list)

    def add(self, step: str, detail: str, **data: Any) -> None:
        self.steps.append(ReasonStep(step=step, detail=detail, data=dict(data)))

    def to_dict(self) -> dict[str, Any]:
        return {"steps": [s.to_dict() for s in self.steps], "step_count": len(self.steps)}


@dataclass
class RoutingDecision:
    expert_id: str
    side: str
    score: float
    no_trade: bool
    reason_trace: ReasonTrace
    expert_scores: list[ExpertScore]
    champion_role: str
    challenger_expert_id: str | None
    cooldown_active: bool
    degradation_active: bool
    formal_params_locked: bool
    risk_gate_honored: bool
    leverage_ai_mutation_blocked: bool
    leverage: int
    ai_override_risk_gate_applied: bool = False
    ai_set_leverage_applied: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.expert_id not in EXPERT_IDS:
            raise ValueError(f"unknown expert_id={self.expert_id}")
        if self.side not in DECISION_SIDES:
            raise ValueError(f"unknown side={self.side}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert_id": self.expert_id,
            "side": self.side,
            "score": self.score,
            "no_trade": self.no_trade,
            "reason_trace": self.reason_trace.to_dict(),
            "expert_scores": [e.to_dict() for e in self.expert_scores],
            "champion_role": self.champion_role,
            "challenger_expert_id": self.challenger_expert_id,
            "cooldown_active": self.cooldown_active,
            "degradation_active": self.degradation_active,
            "formal_params_locked": self.formal_params_locked,
            "risk_gate_honored": self.risk_gate_honored,
            "leverage_ai_mutation_blocked": self.leverage_ai_mutation_blocked,
            "leverage": self.leverage,
            "ai_override_risk_gate_applied": self.ai_override_risk_gate_applied,
            "ai_set_leverage_applied": self.ai_set_leverage_applied,
            "metadata": dict(self.metadata),
        }
