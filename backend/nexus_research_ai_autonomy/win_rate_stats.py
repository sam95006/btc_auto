"""Win rate + performance statistics — honest sample confidence, no gaming."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

LIFECYCLE_PURPOSE_RESEARCH = "RESEARCH_PNL_TRADE"
EXCLUDED_PURPOSES = frozenset({"EXECUTION_CANARY", "LOCAL_SIM", "SHADOW"})


@dataclass
class TradeRecord:
    symbol: str
    side: str
    net_realized: float
    accounting_complete: bool
    lifecycle_purpose: str
    mfe_usdt: float = 0.0
    mfe_capture_ratio: float | None = None

    @property
    def is_win(self) -> bool:
        return self.accounting_complete and self.net_realized > 0

    @property
    def is_loss(self) -> bool:
        return self.accounting_complete and self.net_realized < 0


@dataclass
class PerformanceStats:
    accounting_complete_trades: int = 0
    wins: int = 0
    losses: int = 0
    observed_win_rate: float | None = None
    winrate_sample_status: str = "INSUFFICIENT_SAMPLE_FOR_WINRATE_CLAIM"
    net_pnl: float = 0.0
    expectancy: float | None = None
    profit_factor: float | None = None
    average_win: float | None = None
    average_loss: float | None = None
    max_drawdown: float = 0.0
    long_trades: int = 0
    long_wins: int = 0
    long_losses: int = 0
    long_win_rate: float | None = None
    long_net_pnl: float = 0.0
    short_trades: int = 0
    short_wins: int = 0
    short_losses: int = 0
    short_win_rate: float | None = None
    short_net_pnl: float = 0.0
    mfe_capture_avg: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def lifecycle_to_trade(lifecycle: dict[str, Any]) -> TradeRecord | None:
    purpose = str(lifecycle.get("lifecycle_purpose") or "")
    if purpose in EXCLUDED_PURPOSES or purpose != LIFECYCLE_PURPOSE_RESEARCH:
        return None
    ea = lifecycle.get("exact_pnl_accounting") or {}
    if not ea.get("accounting_complete") and not lifecycle.get("accounting_complete"):
        return None
    pe = lifecycle.get("path_excursion") or {}
    mfe = float(pe.get("mfe_usdt") or 0)
    net = float(ea.get("calculated_net_pnl") or ea.get("net_realized") or 0)
    cap = pe.get("mfe_capture_ratio")
    return TradeRecord(
        symbol=str(lifecycle.get("symbol") or ""),
        side=str(lifecycle.get("side") or "").upper(),
        net_realized=net,
        accounting_complete=True,
        lifecycle_purpose=purpose,
        mfe_usdt=mfe,
        mfe_capture_ratio=float(cap) if cap is not None else None,
    )


def compute_mfe_capture_ratio(
    *,
    mfe_usdt: float,
    realized_favorable_usdt: float,
) -> float | None:
    if mfe_usdt <= 0:
        return None
    return min(1.0, max(0.0, realized_favorable_usdt / mfe_usdt))


def compute_performance_stats(lifecycles: list[dict[str, Any]]) -> PerformanceStats:
    trades: list[TradeRecord] = []
    for lc in lifecycles:
        t = lifecycle_to_trade(lc)
        if t:
            trades.append(t)

    stats = PerformanceStats()
    stats.accounting_complete_trades = len(trades)
    if not trades:
        return stats

    win_pnls = [t.net_realized for t in trades if t.is_win]
    loss_pnls = [t.net_realized for t in trades if t.is_loss]
    stats.wins = len(win_pnls)
    stats.losses = len(loss_pnls)
    stats.net_pnl = sum(t.net_realized for t in trades)

    if stats.accounting_complete_trades >= 30:
        stats.winrate_sample_status = "PROVISIONAL_WINRATE_EVIDENCE"
        stats.observed_win_rate = stats.wins / stats.accounting_complete_trades
    elif stats.accounting_complete_trades > 0:
        stats.observed_win_rate = stats.wins / stats.accounting_complete_trades
        stats.winrate_sample_status = "INSUFFICIENT_SAMPLE_FOR_WINRATE_CLAIM"

    if stats.accounting_complete_trades > 0:
        stats.expectancy = stats.net_pnl / stats.accounting_complete_trades
    if win_pnls:
        stats.average_win = sum(win_pnls) / len(win_pnls)
    if loss_pnls:
        stats.average_loss = sum(loss_pnls) / len(loss_pnls)
    gross_win = sum(win_pnls) if win_pnls else 0.0
    gross_loss = abs(sum(loss_pnls)) if loss_pnls else 0.0
    if gross_loss > 0:
        stats.profit_factor = gross_win / gross_loss

    # max drawdown on cumulative curve
    cum = 0.0
    peak = 0.0
    mdd = 0.0
    for t in trades:
        cum += t.net_realized
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    stats.max_drawdown = mdd

    caps = [t.mfe_capture_ratio for t in trades if t.mfe_capture_ratio is not None]
    if caps:
        stats.mfe_capture_avg = sum(caps) / len(caps)

    for side_key, side_val in (("long", "LONG"), ("short", "SHORT")):
        side_trades = [t for t in trades if t.side in {side_val, side_val.replace("LONG", "BUY").replace("SHORT", "SELL")}]
        if side_val == "LONG":
            side_trades = [t for t in trades if t.side in {"LONG", "BUY"}]
        else:
            side_trades = [t for t in trades if t.side in {"SHORT", "SELL"}]
        n = len(side_trades)
        w = sum(1 for t in side_trades if t.is_win)
        l = sum(1 for t in side_trades if t.is_loss)
        pnl = sum(t.net_realized for t in side_trades)
        wr = w / n if n else None
        if side_key == "long":
            stats.long_trades, stats.long_wins, stats.long_losses = n, w, l
            stats.long_net_pnl = pnl
            stats.long_win_rate = wr
        else:
            stats.short_trades, stats.short_wins, stats.short_losses = n, w, l
            stats.short_net_pnl = pnl
            stats.short_win_rate = wr

    return stats
