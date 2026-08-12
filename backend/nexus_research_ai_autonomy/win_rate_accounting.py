"""Win rate accounting — RESEARCH_PNL_TRADE + ACCOUNTING_COMPLETE only.

n < 30: INSUFFICIENT_SAMPLE_FOR_WINRATE_CLAIM. No win-rate gaming.
Reports expectancy, profit factor, drawdown; LONG/SHORT split.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_research_ai_autonomy.lifecycle_purpose import (
    LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
    is_pnl_bearing,
)

WIN_RATE_SCHEMA = "v18_2_28_win_rate_accounting_v1"
MIN_WINRATE_SAMPLE = 30
INSUFFICIENT_SAMPLE_FOR_WINRATE_CLAIM = "INSUFFICIENT_SAMPLE_FOR_WINRATE_CLAIM"


def _accounting_complete(life: dict[str, Any]) -> bool:
    wr = life.get("wallet_reconciliation") or {}
    if wr.get("WALLET_RECONCILIATION_PASS") is True:
        return True
    ea = life.get("exact_pnl_accounting") or {}
    return bool(ea.get("accounting_complete") or ea.get("ACCOUNTING_COMPLETE"))


def _net_pnl(life: dict[str, Any]) -> float:
    ea = life.get("exact_pnl_accounting") or {}
    if ea.get("calculated_net_pnl") is not None:
        return float(ea["calculated_net_pnl"])
    wr = life.get("wallet_reconciliation") or {}
    if wr.get("actual_wallet_delta") is not None:
        return float(wr["actual_wallet_delta"])
    closed = life.get("exchange_closed_pnl") or {}
    if closed.get("closedPnl") is not None:
        return float(closed["closedPnl"])
    return 0.0


def _side_bucket(life: dict[str, Any]) -> str:
    s = str(life.get("side") or life.get("direction") or "UNKNOWN").upper()
    if s in {"LONG", "BUY"}:
        return "LONG"
    if s in {"SHORT", "SELL"}:
        return "SHORT"
    return "UNKNOWN"


def _side_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    nets = [_net_pnl(t) for t in trades]
    wins = [n for n in nets if n > 0]
    losses = [abs(n) for n in nets if n < 0]
    n = len(trades)
    return {
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "net_pnl": sum(nets),
        "win_rate": (len(wins) / n) if n else None,
        "expectancy": (sum(nets) / n) if n else None,
        "profit_factor": (sum(wins) / sum(losses)) if wins and losses and sum(losses) > 0 else None,
    }


def compute_research_win_rate(lifecycles: list[dict[str, Any]]) -> dict[str, Any]:
    """Account only RESEARCH_PNL_TRADE with complete accounting."""
    eligible = [
        L
        for L in lifecycles
        if is_pnl_bearing(L.get("lifecycle_purpose") or L.get("purpose"))
        and _accounting_complete(L)
    ]
    n = len(eligible)
    nets = [_net_pnl(L) for L in eligible]
    wins = [x for x in nets if x > 0]
    losses = [abs(x) for x in nets if x < 0]

    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in nets:
        cumulative += x
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)

    long_trades = [L for L in eligible if _side_bucket(L) == "LONG"]
    short_trades = [L for L in eligible if _side_bucket(L) == "SHORT"]

    win_rate = (len(wins) / n) if n else None
    expectancy = (sum(nets) / n) if n else None
    pf = (sum(wins) / sum(losses)) if wins and losses and sum(losses) > 0 else None

    claim_status = "ACCOUNTING_COMPLETE"
    if n < MIN_WINRATE_SAMPLE:
        claim_status = INSUFFICIENT_SAMPLE_FOR_WINRATE_CLAIM

    return {
        "schema": WIN_RATE_SCHEMA,
        "lifecycle_purpose_filter": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
        "accounting_complete_only": True,
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate if n >= MIN_WINRATE_SAMPLE else None,
        "win_rate_claim_status": claim_status,
        "expectancy": expectancy,
        "profit_factor": pf,
        "net_pnl": sum(nets),
        "max_drawdown_usdt": max_dd,
        "min_sample_for_winrate_claim": MIN_WINRATE_SAMPLE,
        "win_rate_gaming_blocked": True,
        "long_performance": _side_metrics(long_trades),
        "short_performance": _side_metrics(short_trades),
        "order_ids": [L.get("bybit_orderId") or L.get("order_id") for L in eligible],
    }
