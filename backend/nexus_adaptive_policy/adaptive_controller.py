"""Adaptive policy controller — shadow order intents with fixed leverage."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_adaptive_policy import FIXED_LEVERAGE, MAX_MARGIN, MIN_MARGIN
from backend.nexus_adaptive_policy.constitution import LeverageConstitution
from backend.nexus_adaptive_policy.policy import DynamicTradingPolicy, PolicyDecisionTrace, PolicySnapshot
from backend.nexus_adaptive_policy.similarity import GuardAction, PreTradeMistakeGuard


@dataclass
class ShadowOrderIntent:
    symbol: str
    side: str
    leverage: int
    margin_usd: float
    strategy_id: str
    decision: str
    labels: list[str] = field(default_factory=lambda: ["SHADOW", "NO_EXCHANGE_WRITE", "NOT_LIVE"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "leverage": self.leverage,
            "margin_usd": self.margin_usd,
            "strategy_id": self.strategy_id,
            "decision": self.decision,
            "labels": list(self.labels),
        }


@dataclass
class ControllerResult:
    ok: bool
    intent: ShadowOrderIntent | None = None
    trace: PolicyDecisionTrace | None = None
    skip_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "intent": self.intent.to_dict() if self.intent else None,
            "trace": self.trace.to_dict() if self.trace else None,
            "skip_reason": self.skip_reason,
        }


class AdaptivePolicyController:
    """Produce shadow-only intents; margin bounded; leverage always 25."""

    _trace_seq = 0

    def __init__(
        self,
        policy: DynamicTradingPolicy | None = None,
        guard: PreTradeMistakeGuard | None = None,
    ) -> None:
        self.policy = policy or DynamicTradingPolicy()
        self.constitution = LeverageConstitution()
        self.guard = guard

    def evaluate_entry(
        self,
        *,
        symbol: str,
        side: str,
        ai_suggested_margin: float,
        risk_budget: float,
        stop_distance_cap: float,
        portfolio_remaining: float,
        liquidity_cap: float,
        slippage_cap: float,
        entry_score: float,
        strategy_id: str = "default",
        requested_leverage: int = FIXED_LEVERAGE,
    ) -> ControllerResult:
        lev_verdict = self.constitution.validate_leverage(requested_leverage)
        if not lev_verdict.ok:
            return ControllerResult(ok=False, skip_reason=lev_verdict.violation.value if lev_verdict.violation else "leverage_rejected")

        if not self.policy.entry_passes(entry_score):
            return ControllerResult(ok=False, skip_reason="ENTRY_THRESHOLD_NOT_MET")

        margin = min(
            ai_suggested_margin,
            risk_budget,
            stop_distance_cap,
            portfolio_remaining,
            liquidity_cap,
            slippage_cap,
            float(MAX_MARGIN),
        )
        if self.guard:
            guard_decision = self.guard.evaluate(symbol=symbol, strategy_id=strategy_id)
            margin *= guard_decision.margin_multiplier
            if guard_decision.action == GuardAction.BLOCK:
                return ControllerResult(ok=False, skip_reason="MISTAKE_GUARD_BLOCK")
            if guard_decision.action == GuardAction.SHADOW_ONLY:
                pass  # still shadow; no live path exists

        if margin < MIN_MARGIN:
            return ControllerResult(ok=False, skip_reason="RISK_BUDGET_BELOW_MINIMUM")

        AdaptivePolicyController._trace_seq += 1
        trace = PolicyDecisionTrace(
            trace_id=f"trace_{AdaptivePolicyController._trace_seq:06d}",
            decision="SHADOW_INTENT",
            reason="margin_within_bounds",
            leverage=FIXED_LEVERAGE,
            margin_usd=margin,
            policy_snapshot_id=self.policy.snapshot.snapshot_id,
        )
        intent = ShadowOrderIntent(
            symbol=symbol,
            side=side,
            leverage=FIXED_LEVERAGE,
            margin_usd=margin,
            strategy_id=strategy_id,
            decision="SHADOW_ONLY",
        )
        return ControllerResult(ok=True, intent=intent, trace=trace)
