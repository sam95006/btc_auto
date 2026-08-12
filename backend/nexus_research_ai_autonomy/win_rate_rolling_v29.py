"""V18.2.29 rolling performance stats (last-10 / last-30) for RESEARCH trades."""

from __future__ import annotations

from typing import Any

from backend.nexus_research_ai_autonomy.lifecycle_purpose import LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE, is_pnl_bearing
from backend.nexus_research_ai_autonomy.win_rate_accounting import _accounting_complete, _net_pnl, _side_bucket


def _mfe_capture_ratio(life: dict[str, Any]) -> float | None:
    pe = life.get("path_excursion") or {}
    v = pe.get("MFE_capture_ratio")
    if v is None:
        v = pe.get("mfe_capture_ratio")
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _window_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    nets = [_net_pnl(t) for t in trades]
    wins = [x for x in nets if x > 0]
    losses = [abs(x) for x in nets if x < 0]
    n = len(trades)

    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in nets:
        cumulative += x
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)

    mfe_ratios = [_mfe_capture_ratio(t) for t in trades]
    mfe_ratios = [x for x in mfe_ratios if x is not None]

    return {
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "net_pnl": sum(nets),
        "win_rate": (len(wins) / n) if n else None,
        "expectancy": (sum(nets) / n) if n else None,
        "profit_factor": (sum(wins) / sum(losses)) if wins and losses and sum(losses) > 0 else None,
        "max_drawdown_usdt": max_dd,
        "avg_mfe_capture_ratio": (sum(mfe_ratios) / len(mfe_ratios)) if mfe_ratios else None,
    }


def compute_research_rolling_stats(lifecycles: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute last-10/last-30 for accounting-complete RESEARCH trades only.

    Note: lifecycles are treated as ordered chronologically as provided by the caller.
    """
    eligible = [
        L
        for L in lifecycles
        if is_pnl_bearing(L.get("lifecycle_purpose") or L.get("purpose"))
        and _accounting_complete(L)
    ]
    last_10 = eligible[-10:] if len(eligible) >= 10 else eligible
    last_30 = eligible[-30:] if len(eligible) >= 30 else eligible

    return {
        "schema": "v18_2_29_rolling_win_rate_accounting_v1",
        "lifecycle_purpose_filter": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
        "accounting_complete_only": True,
        "last_10": _window_metrics(last_10),
        "last_30": _window_metrics(last_30),
    }

