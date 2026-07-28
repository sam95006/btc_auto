"""Shadow position lifecycle state machine."""
from __future__ import annotations

from typing import Any

from backend.nexus_global_shadow.contracts import (
    LifecycleState,
    Outcome,
    ShadowPosition,
    assert_transition,
    now_ms,
)

EXIT_REASONS = frozenset(
    {
        "TAKE_PROFIT",
        "STOP_LOSS",
        "TIME_STOP",
        "INVALIDATION",
        "RISK_REDUCTION",
        "DATA_QUALITY_EXIT",
        "REGIME_CHANGE_EXIT",
        "PORTFOLIO_REBALANCE",
        "MANUAL_FIXTURE_EXIT",
        "UNKNOWN",
    }
)


class ShadowLifecycleManager:
    """Shadow-only lifecycle; uses contracts.assert_transition."""

    def transition(self, position: ShadowPosition, new_state: str) -> ShadowPosition:
        assert_transition(position.state, new_state)
        position.state = new_state
        return position

    def open_shadow(
        self,
        position: ShadowPosition,
        entry_price: float | None,
        *,
        fee: float | None = None,
        slippage: float | None = None,
    ) -> ShadowPosition:
        chain = [
            LifecycleState.SIX_ROLE_REVIEWED.value,
            LifecycleState.RISK_APPROVED.value,
            LifecycleState.PORTFOLIO_SELECTED.value,
            LifecycleState.SHADOW_OPEN_PENDING.value,
            LifecycleState.SHADOW_OPEN.value,
        ]
        for nxt in chain:
            self.transition(position, nxt)
        position.entry_time = now_ms()
        position.entry_price = entry_price
        position.simulated_fee = fee
        position.simulated_slippage = slippage
        if entry_price is not None:
            position.mark_series = [entry_price]
        return position

    def simulate_protection(self, position: ShadowPosition, plan: dict[str, Any]) -> ShadowPosition:
        self.transition(position, LifecycleState.PROTECTED_SIMULATED.value)
        position.protection_plan = dict(plan)
        position.exit_policy = dict(plan.get("exit_policy") or {})
        return position

    def request_exit(self, position: ShadowPosition, reason: str) -> ShadowPosition:
        if reason not in EXIT_REASONS:
            reason = "UNKNOWN"
        if position.state == LifecycleState.PROTECTED_SIMULATED.value:
            self.transition(position, LifecycleState.EXIT_PENDING.value)
        elif position.state == LifecycleState.SHADOW_OPEN.value:
            self.transition(position, LifecycleState.EXIT_PENDING.value)
        position.exit_reason = reason
        return position

    def close(
        self,
        position: ShadowPosition,
        exit_price: float | None,
        *,
        fees: float | None = None,
        funding: float | None = None,
        slippage: float | None = None,
    ) -> tuple[ShadowPosition, Outcome]:
        self.transition(position, LifecycleState.SHADOW_CLOSED.value)
        position.exit_time = now_ms()
        position.exit_price = exit_price
        position.fees = fees
        position.funding = funding
        position.slippage = slippage
        gross = None
        net = None
        r_mult = None
        if exit_price is not None and position.entry_price is not None and position.position_size:
            direction_mult = 1 if position.direction == "LONG" else -1
            gross = (exit_price - position.entry_price) * direction_mult * position.position_size
            net = gross
            if fees is not None:
                net -= fees
            if funding is not None:
                net -= funding
            if slippage is not None:
                net -= slippage
            position.gross_pnl = gross
            position.net_pnl = net
        incomplete = exit_price is None or position.entry_price is None
        outcome = Outcome(
            position_id=position.position_id,
            symbol=position.symbol,
            exit_reason=position.exit_reason,
            gross_pnl=gross,
            fees=fees,
            funding=funding,
            slippage=slippage,
            net_pnl=net,
            r_multiple=r_mult,
            incomplete=incomplete,
            completeness="COMPLETE" if not incomplete else "PARTIAL",
        )
        self.transition(position, LifecycleState.OUTCOME_CREATED.value)
        return position, outcome

    def advance_learning_chain(self, position: ShadowPosition) -> ShadowPosition:
        chain = [
            LifecycleState.REFLECTION_CREATED.value,
            LifecycleState.PATCH_PROPOSED.value,
            LifecycleState.REPLAY_VALIDATED.value,
            LifecycleState.OOS_VALIDATED.value,
            LifecycleState.SHADOW_APPLIED.value,
            LifecycleState.ARCHIVED.value,
        ]
        for nxt in chain:
            self.transition(position, nxt)
        return position
