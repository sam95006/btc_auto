"""Real-price shadow execution simulator — no exchange write, fixed 25x."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_adaptive_policy.constitution import LeverageConstitution
from backend.nexus_global_shadow.contracts import LifecycleState, ShadowPosition, new_id, now_ms
from backend.nexus_real_shadow import FIXED_LEVERAGE, MAX_OPEN, MAX_PENDING, SHADOW_LABELS


SHADOW_EXEC_LABELS = list(SHADOW_LABELS)


@dataclass
class ShadowIntent:
    intent_id: str
    symbol: str
    direction: str
    leverage: int
    margin_usdt: float | None
    labels: list[str] = field(default_factory=lambda: list(SHADOW_EXEC_LABELS))
    status: str = "SHADOW_SIMULATED"
    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "leverage": self.leverage,
            "margin_usdt": self.margin_usdt,
            "labels": list(self.labels),
            "status": self.status,
            "correlation_id": self.correlation_id,
            "executed": False,
            "exchange_write": False,
        }


@dataclass
class ProtectionState:
    stop_loss: float | None = None
    take_profit: float | None = None
    trailing_stop: float | None = None
    stop_widened: bool = False
    martingale: bool = False
    averaging_down: bool = False

    def validate(self) -> list[str]:
        violations: list[str] = []
        if self.stop_widened:
            violations.append("stop_widening_forbidden")
        if self.martingale:
            violations.append("martingale_forbidden")
        if self.averaging_down:
            violations.append("averaging_down_forbidden")
        return violations


class RealPriceShadowExecutionSimulator:
    """Simulate shadow entries/exits using public prices only."""

    def __init__(self) -> None:
        self.constitution = LeverageConstitution()
        self.open_positions: dict[str, ShadowPosition] = {}
        self.pending_intents: dict[str, ShadowIntent] = {}
        self.closed_outcomes: list[dict[str, Any]] = []

    def create_intent(
        self,
        *,
        symbol: str,
        direction: str,
        margin_usdt: float | None,
        correlation_id: str | None = None,
    ) -> ShadowIntent | dict[str, Any]:
        lev_verdict = self.constitution.validate_leverage(FIXED_LEVERAGE)
        if not lev_verdict.ok:
            return {"ok": False, "error": lev_verdict.detail, "labels": SHADOW_EXEC_LABELS}
        if len(self.open_positions) >= MAX_OPEN:
            return {"ok": False, "error": "max_open_reached", "labels": SHADOW_EXEC_LABELS}
        if len(self.pending_intents) >= MAX_PENDING:
            return {"ok": False, "error": "max_pending_reached", "labels": SHADOW_EXEC_LABELS}
        intent = ShadowIntent(
            intent_id=new_id("shadow_intent"),
            symbol=symbol,
            direction=direction,
            leverage=FIXED_LEVERAGE,
            margin_usdt=margin_usdt,
            correlation_id=correlation_id,
        )
        self.pending_intents[intent.intent_id] = intent
        return intent

    def simulate_fill(
        self,
        intent: ShadowIntent,
        *,
        entry_price: float | None,
        fee_rate: float | None = None,
        funding_rate: float | None = None,
        slippage_bps: float | None = None,
    ) -> ShadowPosition | dict[str, Any]:
        if entry_price is None:
            return {"ok": False, "error": "missing_entry_price", "labels": SHADOW_EXEC_LABELS}
        pos = ShadowPosition(
            position_id=new_id("shadow_pos"),
            candidate_id=intent.intent_id,
            symbol=intent.symbol,
            direction=intent.direction,
            strategy_id="real_public_shadow",
            regime="UNCERTAIN",
            state=LifecycleState.SHADOW_OPEN.value,
            entry_price=entry_price,
            position_size=1.0,
            risk_budget=0.25,
            source="wave5_real_public_shadow",
            mode="SHADOW",
        )
        pos.protection_plan = {
            "leverage": FIXED_LEVERAGE,
            "labels": list(SHADOW_EXEC_LABELS),
            "fee_rate": fee_rate if fee_rate is not None else "MISSING",
            "funding_rate": funding_rate if funding_rate is not None else "MISSING",
            "slippage_bps": slippage_bps if slippage_bps is not None else "MISSING",
            "correlation_id": intent.correlation_id,
            "executed": False,
            "exchange_write": False,
        }
        self.open_positions[pos.position_id] = pos
        self.pending_intents.pop(intent.intent_id, None)
        return pos

    def simulate_exit(
        self,
        position_id: str,
        *,
        exit_price: float | None,
        reason: str = "PROTECTION_EXIT",
    ) -> dict[str, Any]:
        pos = self.open_positions.pop(position_id, None)
        if not pos:
            return {"ok": False, "error": "position_not_found"}
        outcome = {
            "outcome_id": new_id("shadow_outcome"),
            "position_id": position_id,
            "symbol": pos.symbol,
            "direction": pos.direction,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "reason": reason,
            "pnl": _calc_pnl(pos, exit_price),
            "fee": "MISSING",
            "funding": "MISSING",
            "labels": SHADOW_EXEC_LABELS,
            "executed": False,
            "exchange_write": False,
            "closed_at": now_ms(),
        }
        self.closed_outcomes.append(outcome)
        return outcome


def _calc_pnl(pos: ShadowPosition, exit_price: float | None) -> float | None:
    if exit_price is None or pos.entry_price is None:
        return None
    sign = 1 if pos.direction == "LONG" else -1
    return sign * (exit_price - pos.entry_price) * float(pos.position_size or 1)


class ShadowPositionSupervisor:
    """Monitor open shadow positions for protection exits."""

    def __init__(self, simulator: RealPriceShadowExecutionSimulator | None = None) -> None:
        self.simulator = simulator or RealPriceShadowExecutionSimulator()
        self.protection_by_position: dict[str, ProtectionState] = {}

    def attach_protection(self, position_id: str, *, stop_loss: float | None, take_profit: float | None) -> ProtectionState:
        state = ProtectionState(stop_loss=stop_loss, take_profit=take_profit)
        self.protection_by_position[position_id] = state
        return state

    def evaluate(self, position_id: str, *, mark_price: float | None) -> dict[str, Any]:
        pos = self.simulator.open_positions.get(position_id)
        prot = self.protection_by_position.get(position_id)
        if not pos or not prot:
            return {"action": "HOLD", "reason": "missing_position_or_protection"}
        violations = prot.validate()
        if violations:
            return {"action": "BLOCK", "reason": violations[0]}
        if mark_price is None:
            return {"action": "HOLD", "reason": "missing_mark_price"}
        if prot.stop_loss is not None:
            if pos.direction == "LONG" and mark_price <= prot.stop_loss:
                return self.simulator.simulate_exit(position_id, exit_price=mark_price, reason="STOP_LOSS")
            if pos.direction == "SHORT" and mark_price >= prot.stop_loss:
                return self.simulator.simulate_exit(position_id, exit_price=mark_price, reason="STOP_LOSS")
        if prot.take_profit is not None:
            if pos.direction == "LONG" and mark_price >= prot.take_profit:
                return self.simulator.simulate_exit(position_id, exit_price=mark_price, reason="TAKE_PROFIT")
            if pos.direction == "SHORT" and mark_price <= prot.take_profit:
                return self.simulator.simulate_exit(position_id, exit_price=mark_price, reason="TAKE_PROFIT")
        return {"action": "HOLD", "reason": "within_protection_band"}
