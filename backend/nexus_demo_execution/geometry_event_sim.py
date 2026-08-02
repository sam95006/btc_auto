"""Event-driven Structural Geometry trade simulation — no look-ahead.

Cost Gate pass ≠ trade. Unresolved positions are not wins.
Intrabar SL+TP → adverse-first (conservative).
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Literal

from backend.nexus_demo_execution.session_limits import (
    MIN_NET_REWARD_RISK_RATIO,
    MIN_NET_REWARD_TO_COST,
    TAKER_FEE_RATE_DEFAULT,
)
from backend.nexus_demo_execution.structural_geometry_qualify import (
    CandidateEvidence,
    evaluate_structural_geometry,
)

OutcomeStatus = Literal[
    "ENTRY_NOT_TRIGGERED",
    "ENTRY_FILLED",
    "STOP_LOSS",
    "TAKE_PROFIT",
    "TIME_STOP",
    "TRAILING_EXIT",
    "EARLY_EXIT",
    "UNRESOLVED_AT_DATA_END",
    "COST_GATE_BLOCKED",
    "GEOMETRY_BLOCKED",
]

INTRABAR_METHOD = "ADVERSE_FIRST"
LOOK_AHEAD_CONTAMINATION = False


@dataclass
class Candle:
    ts: float
    open: float
    high: float
    low: float
    close: float


@dataclass
class SimTrade:
    symbol: str
    side: str
    status: OutcomeStatus
    entry_ts: float | None = None
    exit_ts: float | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    stop: float | None = None
    take_profit: float | None = None
    qty: float = 0.0
    gross_pnl: float | None = None
    fees: float | None = None
    spread_cost: float | None = None
    slippage_cost: float | None = None
    funding: float | None = None
    net_pnl: float | None = None
    process_label: str | None = None
    intrabar_resolution_method: str | None = None
    look_ahead_contamination: bool = False


def _fee(notional: float, rate: float) -> float:
    return abs(notional) * rate


def _bps_cost(notional: float, bps: float) -> float:
    return abs(notional) * (bps / 10000.0)


def generate_synthetic_path(
    *,
    entry: float,
    side: str,
    stop: float,
    take_profit: float,
    n: int = 24,
    seed: int = 0,
    resolve: str = "stop",  # stop | tp | unresolved | time
) -> list[Candle]:
    """Synthetic subsequent candles only — no future info at decision time."""
    candles: list[Candle] = []
    px = entry
    buy = side.lower() in {"buy", "long"}
    for i in range(n):
        ts = float(i + 1)
        if resolve == "tp":
            step = (take_profit - entry) / max(8, n // 2)
        elif resolve == "stop":
            step = (stop - entry) / max(8, n // 2)
        elif resolve == "time":
            step = (0.0005 if (seed + i) % 2 == 0 else -0.0005) * entry
        else:
            step = 0.0
        nxt = px + step
        noise = ((seed * 17 + i * 13) % 7 - 3) * entry * 0.00005
        nxt = nxt + noise
        high = max(px, nxt) * (1 + 0.0002)
        low = min(px, nxt) * (1 - 0.0002)
        if i >= n - 3 and resolve in {"tp", "stop"}:
            if buy and resolve == "tp":
                high = max(high, take_profit)
            elif buy and resolve == "stop":
                low = min(low, stop)
            elif (not buy) and resolve == "tp":
                low = min(low, take_profit)
            elif (not buy) and resolve == "stop":
                high = max(high, stop)
        candles.append(Candle(ts=ts, open=px, high=high, low=low, close=nxt))
        px = nxt
    return candles


def simulate_trade(
    *,
    candidate: CandidateEvidence,
    subsequent_candles: list[Candle],
    time_stop_bars: int = 20,
    fee_rate: float | None = None,
    adverse_first: bool = True,
) -> SimTrade:
    """Simulate one candidate with frozen geometry at decision time."""
    geo = evaluate_structural_geometry(candidate)
    if geo.get("geometry_missing") or geo.get("geometry_invalid") or not geo.get("geometry_complete"):
        return SimTrade(symbol=candidate.symbol, side=candidate.side, status="GEOMETRY_BLOCKED")
    if not geo.get("cost_gate_pass"):
        return SimTrade(symbol=candidate.symbol, side=candidate.side, status="COST_GATE_BLOCKED")

    stop = float(geo["stop_price"])
    tp = float(geo["take_profit_price"])
    entry = float(candidate.entry_price)
    qty = float(candidate.qty or 1.0)
    side = candidate.side
    buy = side.lower() in {"buy", "long"}
    rate = float(fee_rate if fee_rate is not None else (candidate.fee_rate or TAKER_FEE_RATE_DEFAULT))
    notional = abs(entry * qty)
    spread = _bps_cost(notional, float(candidate.spread_bps or 0.0))
    slip = _bps_cost(notional, float(candidate.slippage_bps or 0.0))
    entry_fee = _fee(notional, rate)

    if not subsequent_candles:
        return SimTrade(
            symbol=candidate.symbol,
            side=side,
            status="UNRESOLVED_AT_DATA_END",
            entry_price=entry,
            stop=stop,
            take_profit=tp,
            qty=qty,
            look_ahead_contamination=LOOK_AHEAD_CONTAMINATION,
        )

    fill_bar = subsequent_candles[0]
    fill_px = float(fill_bar.open)
    if buy:
        fill_px *= 1 + float(candidate.slippage_bps or 0.0) / 10000.0
    else:
        fill_px *= 1 - float(candidate.slippage_bps or 0.0) / 10000.0

    trade = SimTrade(
        symbol=candidate.symbol,
        side=side,
        status="ENTRY_FILLED",
        entry_ts=fill_bar.ts,
        entry_price=fill_px,
        stop=stop,
        take_profit=tp,
        qty=qty,
        fees=entry_fee,
        spread_cost=spread,
        slippage_cost=slip,
        funding=0.0,
        intrabar_resolution_method=INTRABAR_METHOD if adverse_first else "UNSPECIFIED",
        look_ahead_contamination=LOOK_AHEAD_CONTAMINATION,
    )

    funding_acc = 0.0
    for i, bar in enumerate(subsequent_candles[1:], start=1):
        if i > time_stop_bars:
            trade.status = "TIME_STOP"
            trade.exit_ts = bar.ts
            trade.exit_price = bar.close
            break
        funding_acc += abs(fill_px * qty) * float(candidate.funding_rate or 0.0001) / 24.0

        hit_sl = (bar.low <= stop) if buy else (bar.high >= stop)
        hit_tp = (bar.high >= tp) if buy else (bar.low <= tp)
        if hit_sl and hit_tp:
            if not adverse_first:
                trade.look_ahead_contamination = True
            trade.status = "STOP_LOSS"
            trade.exit_ts = bar.ts
            trade.exit_price = stop
            trade.intrabar_resolution_method = INTRABAR_METHOD
            break
        if hit_sl:
            trade.status = "STOP_LOSS"
            trade.exit_ts = bar.ts
            trade.exit_price = stop
            break
        if hit_tp:
            trade.status = "TAKE_PROFIT"
            trade.exit_ts = bar.ts
            trade.exit_price = tp
            break
    else:
        trade.status = "UNRESOLVED_AT_DATA_END"
        last = subsequent_candles[-1]
        trade.exit_ts = last.ts
        trade.exit_price = last.close

    if trade.exit_price is None or trade.entry_price is None:
        return trade

    exit_notional = abs(float(trade.exit_price) * qty)
    exit_fee = _fee(exit_notional, rate)
    if buy:
        gross = (float(trade.exit_price) - float(trade.entry_price)) * qty
    else:
        gross = (float(trade.entry_price) - float(trade.exit_price)) * qty
    fees = entry_fee + exit_fee
    net = gross - fees - spread - slip - funding_acc
    trade.gross_pnl = round(gross, 8)
    trade.fees = round(fees, 8)
    trade.funding = round(funding_acc, 8)
    trade.net_pnl = round(net, 8)

    if trade.status == "UNRESOLVED_AT_DATA_END":
        trade.process_label = None
        trade.net_pnl = None  # unresolved must not count as win/loss
        trade.gross_pnl = None
    elif net >= 0 and trade.status == "TAKE_PROFIT":
        trade.process_label = "GOOD_PROCESS_WIN"
    elif net < 0 and trade.status in {"STOP_LOSS", "TIME_STOP", "EARLY_EXIT", "TRAILING_EXIT"}:
        trade.process_label = "GOOD_PROCESS_LOSS"
    elif net >= 0:
        trade.process_label = "BAD_PROCESS_WIN"
    else:
        trade.process_label = "BAD_PROCESS_LOSS"
    return trade


def summarize_trades(trades: list[SimTrade], *, min_sample: int = 30) -> dict[str, Any]:
    resolved = [
        t
        for t in trades
        if t.status in {"STOP_LOSS", "TAKE_PROFIT", "TIME_STOP", "TRAILING_EXIT", "EARLY_EXIT"}
        and t.net_pnl is not None
    ]
    unresolved = sum(1 for t in trades if t.status == "UNRESOLVED_AT_DATA_END")
    entry_triggered = sum(
        1
        for t in trades
        if t.status
        in {
            "ENTRY_FILLED",
            "STOP_LOSS",
            "TAKE_PROFIT",
            "TIME_STOP",
            "TRAILING_EXIT",
            "EARLY_EXIT",
            "UNRESOLVED_AT_DATA_END",
        }
    )
    # ENTRY_FILLED alone shouldn't remain after sim; count filled that resolved or unresolved
    filledish = sum(
        1
        for t in trades
        if t.status
        not in {"COST_GATE_BLOCKED", "GEOMETRY_BLOCKED", "ENTRY_NOT_TRIGGERED"}
    )
    nets = [float(t.net_pnl) for t in resolved]
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n <= 0]
    gross_wins = sum(wins) if wins else 0.0
    gross_losses = abs(sum(losses)) if losses else 0.0
    pf = (gross_wins / gross_losses) if gross_losses > 0 else (None if not wins else None)
    eq = 0.0
    peak = 0.0
    mdd = 0.0
    for n in nets:
        eq += n
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    look_ahead = any(t.look_ahead_contamination for t in trades)
    out: dict[str, Any] = {
        "candidate_count": len(trades),
        "entry_triggered_count": filledish,
        "simulated_trade_count": len(resolved),
        "unresolved_count": unresolved,
        "gross_pnl": round(sum(float(t.gross_pnl or 0) for t in resolved), 8) if resolved else None,
        "fees": round(sum(float(t.fees or 0) for t in resolved), 8) if resolved else None,
        "spread_cost": round(sum(float(t.spread_cost or 0) for t in resolved), 8) if resolved else None,
        "slippage_cost": round(sum(float(t.slippage_cost or 0) for t in resolved), 8) if resolved else None,
        "funding": round(sum(float(t.funding or 0) for t in resolved), 8) if resolved else None,
        "net_pnl": round(sum(nets), 8) if resolved else None,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(resolved)) if resolved else None,
        "profit_factor": (None if pf is None else round(pf, 6)),
        "expectancy": (statistics.fmean(nets) if nets else None),
        "maximum_drawdown": (round(mdd, 8) if resolved else None),
        "GOOD_PROCESS_WIN": sum(1 for t in resolved if t.process_label == "GOOD_PROCESS_WIN"),
        "GOOD_PROCESS_LOSS": sum(1 for t in resolved if t.process_label == "GOOD_PROCESS_LOSS"),
        "BAD_PROCESS_WIN": sum(1 for t in resolved if t.process_label == "BAD_PROCESS_WIN"),
        "BAD_PROCESS_LOSS": sum(1 for t in resolved if t.process_label == "BAD_PROCESS_LOSS"),
        "look_ahead_contamination": look_ahead,
        "intrabar_resolution_method": INTRABAR_METHOD,
        "floors_unchanged": {
            "MIN_NET_REWARD_RISK_RATIO": MIN_NET_REWARD_RISK_RATIO,
            "MIN_NET_REWARD_TO_COST": MIN_NET_REWARD_TO_COST,
        },
    }
    if look_ahead:
        out["qualification"] = "FAILED"
        out["status"] = "LOOK_AHEAD_CONTAMINATION"
    elif len(resolved) == 0:
        out["status"] = "ZERO_SIMULATION"
        out["performance_status"] = "ZERO_SIMULATION"
    elif len(resolved) < min_sample:
        out["status"] = "INSUFFICIENT_OOS_SAMPLE"
        out["performance_status"] = "INSUFFICIENT_SAMPLE"
    else:
        out["status"] = "PERFORMANCE_COMPUTED"
        out["performance_status"] = "COMPUTED"
    return out


def run_event_driven_folds(
    candidates: list[CandidateEvidence],
    *,
    min_sample: int = 30,
) -> dict[str, Any]:
    """Three chronological folds; OOS untouched; parameters not tuned on OOS."""
    ordered = sorted(candidates, key=lambda c: float(c.ts or 0.0))
    n = len(ordered)
    i_train_end = int(n * 0.40)
    i_val_end = int(n * 0.55)
    i_oos1_end = int(n * 0.70)
    i_oos2_end = int(n * 0.85)

    def _sim_set(rows: list[CandidateEvidence], tag: str) -> tuple[list[SimTrade], dict[str, Any]]:
        trades: list[SimTrade] = []
        for idx, c in enumerate(rows):
            geo = evaluate_structural_geometry(c)
            if not geo.get("cost_gate_pass") or not geo.get("geometry_complete"):
                trades.append(
                    SimTrade(
                        symbol=c.symbol,
                        side=c.side,
                        status="COST_GATE_BLOCKED" if not geo.get("cost_gate_pass") else "GEOMETRY_BLOCKED",
                    )
                )
                continue
            resolve = ("tp", "stop", "time", "unresolved")[idx % 4]
            path = generate_synthetic_path(
                entry=float(c.entry_price),
                side=c.side,
                stop=float(geo["stop_price"]),
                take_profit=float(geo["take_profit_price"]),
                n=24,
                seed=idx + int(c.ts or 0),
                resolve=resolve if resolve != "unresolved" else "time",
            )
            if resolve == "unresolved":
                path = path[:6]
            trades.append(simulate_trade(candidate=c, subsequent_candles=path))
        summary = summarize_trades(trades, min_sample=min_sample)
        summary["fold_tag"] = tag
        summary["geometry_complete_count"] = sum(
            1 for c in rows if evaluate_structural_geometry(c).get("geometry_complete")
        )
        summary["cost_gate_pass_count"] = sum(
            1 for c in rows if evaluate_structural_geometry(c).get("cost_gate_pass")
        )
        return trades, summary

    train_rows = ordered[:i_train_end]
    val_rows = ordered[i_train_end:i_val_end]
    oos_rows = ordered[i_val_end:i_oos1_end]
    fold2 = ordered[i_oos1_end:i_oos2_end]
    fold3 = ordered[i_oos2_end:]

    _, train_s = _sim_set(train_rows, "train")
    _, val_s = _sim_set(val_rows, "validation")
    oos_trades, oos_s = _sim_set(oos_rows, "oos_primary")
    _, f2 = _sim_set(fold2, "oos_fold2")
    _, f3 = _sim_set(fold3, "oos_fold3")

    if oos_s.get("look_ahead_contamination"):
        oos_status = "OOS_PERFORMANCE_FAILED"
    elif (oos_s.get("simulated_trade_count") or 0) == 0:
        oos_status = "OOS_FRAMEWORK_VALIDATED"
    elif oos_s.get("net_pnl") is None or oos_s.get("profit_factor") is None or oos_s.get("expectancy") is None:
        if (oos_s.get("simulated_trade_count") or 0) < min_sample:
            oos_status = "OOS_INSUFFICIENT_SAMPLE"
        else:
            oos_status = "OOS_FRAMEWORK_VALIDATED"
    elif (oos_s.get("simulated_trade_count") or 0) < min_sample:
        oos_status = "OOS_INSUFFICIENT_SAMPLE"
    else:
        # Synthetic forced paths prove the simulator wiring, not market OOS edge.
        # OOS_PERFORMANCE_VALIDATED requires path_source=MARKET_CANDLES (not yet supplied).
        oos_status = "OOS_FRAMEWORK_VALIDATED"
        oos_s["synthetic_simulation_only"] = True
        oos_s["performance_fields_from_synthetic"] = True
        oos_s["oos_performance_validated_blocked_reason"] = (
            "SYNTHETIC_PATH_NOT_MARKET_OOS — metrics populated for simulator proof only"
        )

    oos_s["oos_status"] = oos_status
    oos_s["path_source"] = "SYNTHETIC_FORCED"
    if (val_s.get("simulated_trade_count") or 0) == 0:
        wf_status = "WALK_FORWARD_FRAMEWORK_VALIDATED"
    elif val_s.get("net_pnl") is None:
        wf_status = "WALK_FORWARD_FRAMEWORK_VALIDATED"
    elif (val_s.get("simulated_trade_count") or 0) < min_sample:
        wf_status = "WALK_FORWARD_INSUFFICIENT_SAMPLE"
    else:
        wf_status = "WALK_FORWARD_PERFORMANCE_COMPUTED"
        val_s["synthetic_simulation_only"] = True
    val_s["walk_forward_status"] = wf_status
    val_s["path_source"] = "SYNTHETIC_FORCED"

    return {
        "diagnostic_only_cost_gate_pass_is_not_a_trade": True,
        "intrabar_resolution_method": INTRABAR_METHOD,
        "look_ahead_contamination": False,
        "train": train_s,
        "walk_forward": val_s,
        "oos": oos_s,
        "oos_fold2": f2,
        "oos_fold3": f3,
        "oos_status": oos_status,
        "walk_forward_status": wf_status,
        "oos_trades_sample": [
            {
                "symbol": t.symbol,
                "status": t.status,
                "net_pnl": t.net_pnl,
                "process_label": t.process_label,
            }
            for t in oos_trades[:5]
        ],
        "risk_review_status": "RISK_REVIEW_PENDING_FOUNDER",
        "shadow_status": "NOT_APPLIED",
        "qualification_complete": False,
    }


def classify_oos_status(*, trade_simulation_count: int, performance: dict[str, Any] | None) -> str:
    """Honest OOS vocabulary — zero/null simulation cannot become OOS_VALIDATED."""
    perf = performance or {}
    if trade_simulation_count <= 0:
        return "OOS_FRAMEWORK_VALIDATED"
    required = ("net_pnl", "profit_factor", "expectancy", "maximum_drawdown", "win_rate")
    if any(perf.get(k) is None for k in required):
        return "OOS_FRAMEWORK_VALIDATED"
    return "OOS_PERFORMANCE_COMPUTED"
