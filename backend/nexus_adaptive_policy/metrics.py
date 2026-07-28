"""Learning metrics — truthful target evaluation, never fake achievement."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.nexus_adaptive_policy import TARGET_NET_OOS_WIN_RATE
from backend.nexus_adaptive_policy.trade_case import ProcessQualityVerdict, TradeCase


class TargetStatus(str, Enum):
    TARGET_NOT_REACHED = "TARGET_NOT_REACHED"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    PROMISING = "PROMISING"
    TARGET_REACHED_SHADOW_ONLY = "TARGET_REACHED_SHADOW_ONLY"


MIN_OOS_SAMPLE = 30


@dataclass
class LearningMetricsSnapshot:
    sample_size: int = 0
    net_oos_win_rate: float = 0.0
    cost_adjusted_win_rate: float = 0.0
    expectancy: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    mistake_recurrence_rate: float = 0.0
    bad_process_rate: float = 0.0
    target_status: TargetStatus = TargetStatus.INSUFFICIENT_SAMPLE
    target_net_oos_win_rate: float = TARGET_NET_OOS_WIN_RATE
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_size": self.sample_size,
            "net_oos_win_rate": self.net_oos_win_rate,
            "cost_adjusted_win_rate": self.cost_adjusted_win_rate,
            "expectancy": self.expectancy,
            "profit_factor": self.profit_factor,
            "max_drawdown_pct": self.max_drawdown_pct,
            "mistake_recurrence_rate": self.mistake_recurrence_rate,
            "bad_process_rate": self.bad_process_rate,
            "target_status": self.target_status.value,
            "target_net_oos_win_rate": self.target_net_oos_win_rate,
            "metadata": dict(self.metadata),
        }


class LearningMetricsCalculator:
    """Compute cost-adjusted OOS metrics from trade cases."""

    BAD_PROCESS = {
        ProcessQualityVerdict.BAD_PROCESS_WIN,
        ProcessQualityVerdict.BAD_PROCESS_LOSS,
    }

    def compute(
        self,
        cases: list[TradeCase],
        *,
        costs_usd: float = 0.0,
        recurring_mistakes: int = 0,
        peak_equity: float = 1000.0,
        trough_equity: float = 1000.0,
    ) -> LearningMetricsSnapshot:
        n = len(cases)
        if n == 0:
            return LearningMetricsSnapshot(target_status=TargetStatus.INSUFFICIENT_SAMPLE)

        wins = sum(1 for c in cases if c.is_win())
        gross_profit = sum(c.pnl_usd for c in cases if c.pnl_usd > 0)
        gross_loss = abs(sum(c.pnl_usd for c in cases if c.pnl_usd < 0))
        net_pnl = sum(c.pnl_usd for c in cases) - costs_usd
        net_wins = sum(1 for c in cases if c.pnl_usd - (costs_usd / max(n, 1)) > 0)
        win_rate = wins / n
        cost_adj = net_wins / n
        expectancy = net_pnl / n
        pf = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
        dd = 0.0
        if peak_equity > 0:
            dd = max(0.0, (peak_equity - trough_equity) / peak_equity * 100.0)
        bad_process = sum(1 for c in cases if c.process_verdict in self.BAD_PROCESS)
        bad_rate = bad_process / n
        recurrence = recurring_mistakes / n if n else 0.0

        status = self._target_status(n, cost_adj)
        return LearningMetricsSnapshot(
            sample_size=n,
            net_oos_win_rate=win_rate,
            cost_adjusted_win_rate=cost_adj,
            expectancy=expectancy,
            profit_factor=pf,
            max_drawdown_pct=dd,
            mistake_recurrence_rate=recurrence,
            bad_process_rate=bad_rate,
            target_status=status,
        )

    def _target_status(self, n: int, cost_adj: float) -> TargetStatus:
        if n < MIN_OOS_SAMPLE:
            return TargetStatus.INSUFFICIENT_SAMPLE
        if cost_adj >= TARGET_NET_OOS_WIN_RATE:
            return TargetStatus.TARGET_REACHED_SHADOW_ONLY
        if cost_adj >= TARGET_NET_OOS_WIN_RATE * 0.85:
            return TargetStatus.PROMISING
        return TargetStatus.TARGET_NOT_REACHED
