"""P0 performance report from trading.db trade results (CLI + API)."""

from __future__ import annotations

from datetime import datetime


def _safe_float(value):
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def build_performance_report(runtime_store, limit=500):
    trade_results = list(runtime_store.recent_trade_results(limit=limit))
    if not trade_results:
        return {
            "generated_at": _now(),
            "ready": False,
            "reason": "no_trade_results",
            "sample_size": 0,
        }

    pnls = [_safe_float(item.get("pnl")) for item in trade_results]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = len(wins) / len(pnls)
    total_pnl = sum(pnls)
    avg_pnl = total_pnl / len(pnls)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses)) or 1e-9
    profit_factor = gross_win / gross_loss

    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for pnl in reversed(pnls):
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    by_fleet = {}
    for item in trade_results:
        fleet = str(item.get("fleet") or "UNKNOWN").upper()
        bucket = by_fleet.setdefault(fleet, {"trades": 0, "wins": 0, "pnl": 0.0})
        bucket["trades"] += 1
        pnl = _safe_float(item.get("pnl"))
        bucket["pnl"] += pnl
        if pnl > 0:
            bucket["wins"] += 1

    fleet_summary = {
        fleet: {
            "trades": data["trades"],
            "win_rate": round(data["wins"] / data["trades"], 4) if data["trades"] else 0.0,
            "total_pnl": round(data["pnl"], 4),
        }
        for fleet, data in by_fleet.items()
    }

    from backend.analytics.walk_forward_evaluator import WalkForwardEvaluator

    walk_forward = WalkForwardEvaluator().evaluate(trade_results)
    validation_events = runtime_store.recent_trade_validation_events(limit=200)
    blocks = sum(1 for item in validation_events if not item.get("approved"))

    return {
        "generated_at": _now(),
        "ready": len(trade_results) >= 10,
        "sample_size": len(trade_results),
        "win_rate": round(win_rate, 4),
        "avg_pnl": round(avg_pnl, 4),
        "total_pnl": round(total_pnl, 4),
        "profit_factor": round(profit_factor, 4),
        "max_drawdown": round(max_drawdown, 4),
        "fleet_summary": fleet_summary,
        "walk_forward": walk_forward,
        "validation_block_rate": round(blocks / max(len(validation_events), 1), 4),
        "hint": "Use 30-90 days testnet sample before live; win_rate alone is not enough.",
    }


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    from backend.services.runtime_store import runtime_store

    print(json.dumps(build_performance_report(runtime_store), ensure_ascii=False, indent=2))
