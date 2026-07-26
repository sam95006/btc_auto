"""Daily / weekly risk controllers for autonomous Demo VALIDATION tier."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RiskWindowState:
    equity_start: float
    high_water_mark: float
    realized_pnl: float = 0.0
    consecutive_losses: int = 0
    trade_count: int = 0
    paused: bool = False
    pause_reason: str = ""
    updated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "equityStart": self.equity_start,
            "highWaterMark": self.high_water_mark,
            "realizedPnl": self.realized_pnl,
            "consecutiveLosses": self.consecutive_losses,
            "tradeCount": self.trade_count,
            "paused": self.paused,
            "pauseReason": self.pause_reason,
            "updatedAtMs": self.updated_at_ms,
        }


class AutonomousDemoRiskBudget:
    """VALIDATION defaults: 0.25–0.5% risk, high-conf ≤0.75%; daily 1.5%; weekly DD 4%."""

    def __init__(
        self,
        *,
        equity: float,
        max_daily_loss_pct: float = 1.5,
        max_weekly_drawdown_pct: float = 4.0,
        max_consecutive_losses: int = 3,
        base_risk_pct: float = 0.5,
        high_conf_risk_pct: float = 0.75,
    ) -> None:
        self.equity = float(equity)
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_weekly_drawdown_pct = max_weekly_drawdown_pct
        self.max_consecutive_losses = max_consecutive_losses
        self.base_risk_pct = base_risk_pct
        self.high_conf_risk_pct = high_conf_risk_pct
        self.daily = RiskWindowState(equity, equity)
        self.weekly = RiskWindowState(equity, equity)

    def risk_pct_for_confidence(self, confidence: float) -> float:
        if confidence >= 80:
            return min(self.high_conf_risk_pct, 0.75)
        if confidence >= 72:
            return self.base_risk_pct
        return max(0.25, self.base_risk_pct * 0.7)

    def allow_new_order(self) -> tuple[bool, str | None]:
        if self.daily.paused:
            return False, self.daily.pause_reason or "daily_paused"
        if self.weekly.paused:
            return False, self.weekly.pause_reason or "weekly_paused"
        if self.daily.consecutive_losses >= self.max_consecutive_losses:
            return False, "max_consecutive_losses"
        return True, None

    def record_outcome(self, net_pnl: float, *, equity_now: float | None = None) -> None:
        eq = float(equity_now if equity_now is not None else self.equity + self.daily.realized_pnl + net_pnl)
        self.daily.realized_pnl += net_pnl
        self.weekly.realized_pnl += net_pnl
        self.daily.trade_count += 1
        self.weekly.trade_count += 1
        self.daily.high_water_mark = max(self.daily.high_water_mark, eq)
        self.weekly.high_water_mark = max(self.weekly.high_water_mark, eq)
        if net_pnl < 0:
            self.daily.consecutive_losses += 1
        else:
            self.daily.consecutive_losses = 0

        daily_loss_pct = -min(0.0, self.daily.realized_pnl) / max(self.daily.equity_start, 1e-9) * 100.0
        if daily_loss_pct >= self.max_daily_loss_pct:
            self.daily.paused = True
            self.daily.pause_reason = f"max_daily_loss:{daily_loss_pct:.3f}%"

        dd = (self.weekly.high_water_mark - eq) / max(self.weekly.high_water_mark, 1e-9) * 100.0
        if dd >= self.max_weekly_drawdown_pct:
            self.weekly.paused = True
            self.weekly.pause_reason = f"max_weekly_drawdown:{dd:.3f}%"

        self.daily.updated_at_ms = int(time.time() * 1000)
        self.weekly.updated_at_ms = int(time.time() * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "equity": self.equity,
            "baseRiskPct": self.base_risk_pct,
            "highConfRiskPct": self.high_conf_risk_pct,
            "maxDailyLossPct": self.max_daily_loss_pct,
            "maxWeeklyDrawdownPct": self.max_weekly_drawdown_pct,
            "maxConsecutiveLosses": self.max_consecutive_losses,
            "daily": self.daily.to_dict(),
            "weekly": self.weekly.to_dict(),
            "riskTier": "VALIDATION",
        }
