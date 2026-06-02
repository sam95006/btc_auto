"""Performance report from trading.db trade results (runtime + API)."""

from __future__ import annotations

from datetime import datetime


def _safe_float(value, default=0.0):
    try:
        return float(value if value is not None else default)
    except Exception:
        return float(default)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def build_performance_report(runtime_store, limit=500, research_gate=None):
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
    from config.fee_churn_config import FUTURES_TAKER_FEE_BPS

    walk_forward = WalkForwardEvaluator().evaluate(trade_results)
    validation_events = runtime_store.recent_trade_validation_events(limit=200)
    blocks = sum(1 for item in validation_events if not item.get("approved"))

    fees_estimated = 0.0
    for item in trade_results:
        notional = abs(_safe_float(item.get("margin"))) * _safe_float(item.get("leverage"), 1.0)
        fees_estimated += notional * (FUTURES_TAKER_FEE_BPS / 10000.0) * 2.0
    fee_to_pnl_ratio = abs(fees_estimated / total_pnl) if abs(total_pnl) > 1e-9 else None

    by_strategy = {}
    for item in trade_results:
        key = str(item.get("strategy_key") or "unknown")
        bucket = by_strategy.setdefault(key, {"trades": 0, "wins": 0, "pnl": 0.0})
        bucket["trades"] += 1
        pnl = _safe_float(item.get("pnl"))
        bucket["pnl"] += pnl
        if pnl > 0:
            bucket["wins"] += 1
    strategy_summary = {
        key: {
            "trades": data["trades"],
            "win_rate": round(data["wins"] / data["trades"], 4) if data["trades"] else 0.0,
            "total_pnl": round(data["pnl"], 4),
        }
        for key, data in by_strategy.items()
    }

    tca_samples = [
        item
        for item in trade_results
        if item.get("expected_slippage_bps") is not None and item.get("actual_slippage_bps") is not None
    ]
    tca_summary = None
    if tca_samples:
        deltas = [
            _safe_float(item.get("actual_slippage_bps")) - _safe_float(item.get("expected_slippage_bps"))
            for item in tca_samples
        ]
        tca_summary = {
            "sample_size": len(tca_samples),
            "avg_delta_bps": round(sum(deltas) / len(deltas), 4),
            "worst_delta_bps": round(max(deltas, key=abs), 4),
        }

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
        "strategy_summary": strategy_summary,
        "estimated_fees_usd": round(fees_estimated, 4),
        "fee_to_abs_pnl_ratio": round(fee_to_pnl_ratio, 4) if fee_to_pnl_ratio is not None else None,
        "tca_summary": tca_summary,
        "walk_forward": walk_forward,
        "research_gate": dict(research_gate or {}),
        "validation_block_rate": round(blocks / max(len(validation_events), 1), 4),
        "hint": "Use 30-90 days testnet sample before live; win_rate alone is not enough.",
    }
