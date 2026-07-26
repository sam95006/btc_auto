"""Position lifecycle monitor + exit policies for autonomous Demo."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExitReason(str, Enum):
    HARD_STOP = "HARD_STOP"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    TIME_STOP = "TIME_STOP"
    REGIME_INVALIDATION = "REGIME_INVALIDATION"
    SIGNAL_REVERSAL = "SIGNAL_REVERSAL"
    SPREAD_LIQUIDITY_EMERGENCY = "SPREAD_LIQUIDITY_EMERGENCY"
    SYSTEM_HEALTH_EMERGENCY = "SYSTEM_HEALTH_EMERGENCY"
    MANUAL_KILL_SWITCH = "MANUAL_KILL_SWITCH"
    NONE = "NONE"


@dataclass
class PositionSnapshot:
    symbol: str
    side: str  # Buy | Sell
    size: float
    entry_price: float
    mark_price: float
    unrealised_pnl: float
    liquidation_price: float | None
    stop_loss: float | None
    take_profit: float | None
    opened_at_ms: int
    protection_verified: bool = False

    def distance_to_liq_pct(self) -> float | None:
        if not self.liquidation_price or self.entry_price <= 0:
            return None
        return abs(self.mark_price - self.liquidation_price) / self.entry_price * 100.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "size": self.size,
            "entryPrice": self.entry_price,
            "markPrice": self.mark_price,
            "unrealisedPnl": self.unrealised_pnl,
            "liquidationPrice": self.liquidation_price,
            "stopLoss": self.stop_loss,
            "takeProfit": self.take_profit,
            "openedAtMs": self.opened_at_ms,
            "protectionVerified": self.protection_verified,
            "distanceToLiqPct": self.distance_to_liq_pct(),
        }


@dataclass
class ExitDecision:
    should_exit: bool
    reason: ExitReason
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "shouldExit": self.should_exit,
            "reason": self.reason.value,
            "detail": self.detail,
        }


@dataclass
class LifecyclePolicy:
    max_hold_ms: int = 6 * 60 * 60 * 1000
    trailing_activate_r: float = 1.0
    trailing_giveback_pct: float = 0.4
    max_spread_bps_emergency: float = 40.0
    min_liq_distance_pct: float = 1.0


class DemoPositionLifecycleController:
    """Evaluate exits; does not place orders itself."""

    def __init__(self, policy: LifecyclePolicy | None = None) -> None:
        self.policy = policy or LifecyclePolicy()
        self._peak_favorable_pct: dict[str, float] = {}

    def evaluate(
        self,
        pos: PositionSnapshot,
        *,
        stop_distance_pct: float,
        spread_bps: float = 0.0,
        regime: str = "",
        signal_reversed: bool = False,
        system_healthy: bool = True,
        emergency_stop: bool = False,
        now_ms: int | None = None,
    ) -> ExitDecision:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        if emergency_stop:
            return ExitDecision(True, ExitReason.MANUAL_KILL_SWITCH, "emergency_stop")
        if not system_healthy:
            return ExitDecision(True, ExitReason.SYSTEM_HEALTH_EMERGENCY, "system_unhealthy")
        if spread_bps >= self.policy.max_spread_bps_emergency:
            return ExitDecision(True, ExitReason.SPREAD_LIQUIDITY_EMERGENCY, f"spread={spread_bps}")
        if signal_reversed:
            return ExitDecision(True, ExitReason.SIGNAL_REVERSAL, "signal_reversed")
        if regime in {"EVENT_RISK", "LOW_LIQUIDITY", "UNCERTAIN"}:
            return ExitDecision(True, ExitReason.REGIME_INVALIDATION, f"regime={regime}")
        if now - pos.opened_at_ms >= self.policy.max_hold_ms:
            return ExitDecision(True, ExitReason.TIME_STOP, "max_hold")

        # Hard stop / TP vs mark (exchange protection should already exist)
        if pos.stop_loss:
            if pos.side == "Buy" and pos.mark_price <= pos.stop_loss:
                return ExitDecision(True, ExitReason.HARD_STOP, "mark<=stop")
            if pos.side == "Sell" and pos.mark_price >= pos.stop_loss:
                return ExitDecision(True, ExitReason.HARD_STOP, "mark>=stop")
        if pos.take_profit:
            if pos.side == "Buy" and pos.mark_price >= pos.take_profit:
                return ExitDecision(True, ExitReason.TAKE_PROFIT, "mark>=tp")
            if pos.side == "Sell" and pos.mark_price <= pos.take_profit:
                return ExitDecision(True, ExitReason.TAKE_PROFIT, "mark<=tp")

        # Trailing
        if pos.entry_price > 0:
            if pos.side == "Buy":
                fav = (pos.mark_price - pos.entry_price) / pos.entry_price * 100.0
            else:
                fav = (pos.entry_price - pos.mark_price) / pos.entry_price * 100.0
            peak = max(self._peak_favorable_pct.get(pos.symbol, 0.0), fav)
            self._peak_favorable_pct[pos.symbol] = peak
            activate = stop_distance_pct * self.policy.trailing_activate_r
            if peak >= activate and (peak - fav) >= self.policy.trailing_giveback_pct:
                return ExitDecision(True, ExitReason.TRAILING_STOP, f"peak={peak:.3f} fav={fav:.3f}")

        liq_d = pos.distance_to_liq_pct()
        if liq_d is not None and liq_d < self.policy.min_liq_distance_pct:
            return ExitDecision(True, ExitReason.SYSTEM_HEALTH_EMERGENCY, f"liq_too_close={liq_d:.3f}")

        if not pos.protection_verified:
            # Do not exit solely for missing local verification — flag via detail.
            return ExitDecision(False, ExitReason.NONE, "protection_unverified_continue_monitor")

        return ExitDecision(False, ExitReason.NONE, "hold")
