#!/usr/bin/env python3
"""Read-only audit of recent RESEARCH_PNL_TRADE closed positions from Bybit Demo.

Requires BYBIT_DEMO_API_KEY + BYBIT_DEMO_API_SECRET in env (or NEXUS_DEMO_ENV_FILE).
Outputs honest per-trade rows and aggregate summary — no inferred unavailable fields.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_demo_execution.pnl_accounting import build_exact_pnl_breakdown
from backend.nexus_research_ai_autonomy.bybit_demo_real_transport import load_demo_env
from backend.nexus_research_ai_autonomy.cloud_paths_v301 import campaign_root, resolve_demo_env_path
from backend.nexus_research_ai_autonomy.trade_completion_v30 import (
    REGIME,
    STRATEGY_FAMILY,
    TARGET_PCT,
    STOP_PCT,
    build_setup_signature,
    load_last_trade_closure,
)
from backend.nexus_research_ai_autonomy.same_setup_reentry_guard import closure_path
from backend.nexus_demo_execution.demo_write_client import DemoWriteClient

P0_ROOT_CAUSES = (
    "DIRECTION_WRONG",
    "ENTRY_TOO_EARLY",
    "ENTRY_TOO_LATE",
    "NOISE_ENTRY",
    "FALSE_BREAKOUT",
    "AMBIGUOUS_DIRECTION",
    "REGIME_MISMATCH",
    "LOW_ACTIVITY",
    "LIQUIDITY_WEAK",
    "COST_DOMINATED",
    "STOP_TOO_TIGHT",
    "HORIZON_MISMATCH",
    "EXIT_GIVEBACK",
    "EXCHANGE_ACCOUNTING_INCOMPLETE",
    "UNDETERMINED",
)


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pair_round_trips(closed_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group closed-pnl rows into round-trip trades (entry+exit legs)."""
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in closed_rows:
        sym = str(row.get("symbol") or "")
        if sym:
            by_symbol[sym].append(row)
    trades: list[dict[str, Any]] = []
    for sym, rows in by_symbol.items():
        rows_sorted = sorted(
            rows,
            key=lambda r: int(r.get("updatedTime") or r.get("createdTime") or 0),
            reverse=True,
        )
        for row in rows_sorted:
            trades.append(row)
    trades.sort(
        key=lambda r: int(r.get("updatedTime") or r.get("createdTime") or 0),
        reverse=True,
    )
    return trades


EXCHANGE_ONLY_CAUSES = frozenset(
    {
        "COST_DOMINATED",
        "VERY_SHORT_HOLD",
        "REPEATED_SYMBOL_CHURN",
        "ACCOUNTING_INCOMPLETE",
        "GROSS_POSITIVE_NET_NEGATIVE",
    }
)


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2.0


def _percentile(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    idx = int(max(0, min(len(s) - 1, round(p * (len(s) - 1)))))
    return s[idx]


def _classify_loss_root_causes(row: dict[str, Any], *, net: float | None, hold_sec: float | None) -> list[dict[str, str]]:
    """Exchange-only classifications with evidence level — no fabricated direction diagnosis."""
    if net is None or net >= 0:
        return []
    tags: list[dict[str, str]] = []
    open_fee = abs(_f(row.get("openFee")) or 0.0)
    close_fee = abs(_f(row.get("closeFee")) or 0.0)
    fees = open_fee + close_fee
    closed_pnl = _f(row.get("closedPnl"))
    gross = _f(row.get("_gross_price_pnl"))
    acct = row.get("_accounting_complete")

    if acct is False:
        tags.append({"cause": "ACCOUNTING_INCOMPLETE", "evidence_level": "CONFIRMED"})
    if net < 0 and fees > 0 and (closed_pnl is not None and abs(closed_pnl) <= fees * 1.05):
        tags.append({"cause": "COST_DOMINATED", "evidence_level": "CONFIRMED"})
    elif net < 0 and gross is not None and abs(gross) < fees:
        tags.append({"cause": "COST_DOMINATED", "evidence_level": "SUPPORTED"})
    if gross is not None and gross > 0 and net < 0:
        tags.append({"cause": "GROSS_POSITIVE_NET_NEGATIVE", "evidence_level": "CONFIRMED"})
    if hold_sec is not None and hold_sec < 60:
        tags.append({"cause": "VERY_SHORT_HOLD", "evidence_level": "CONFIRMED"})
    if row.get("_same_symbol_consecutive"):
        tags.append({"cause": "REPEATED_SYMBOL_CHURN", "evidence_level": "SUPPORTED"})
    if not tags:
        tags.append({"cause": "UNDETERMINED", "evidence_level": "UNDETERMINED"})
    return tags


def _churn_risk_distribution(
    *,
    trades: list[dict[str, Any]],
    symbol_concentration: dict[str, int],
    median_hold: float | None,
    under_30s: int,
    fee_drag_median: float | None,
) -> dict[str, Any]:
    """Report churn distribution — no automatic production threshold."""
    total = len(trades)
    top_sym = max(symbol_concentration.items(), key=lambda kv: kv[1]) if symbol_concentration else (None, 0)
    conc_ratio = (top_sym[1] / total) if total and top_sym[1] else 0.0
    risk = "LOW"
    if total >= 5:
        if conc_ratio >= 0.5 or (median_hold is not None and median_hold < 45) or under_30s >= max(3, total // 3):
            risk = "HIGH"
        elif conc_ratio >= 0.35 or (median_hold is not None and median_hold < 90):
            risk = "MEDIUM"
    return {
        "CHURN_RISK": risk,
        "distribution": {
            "top_symbol": top_sym[0],
            "top_symbol_share": round(conc_ratio, 4),
            "median_hold_sec": median_hold,
            "under_30s_share": round(under_30s / total, 4) if total else None,
            "median_fee_drag_per_round_trip": fee_drag_median,
        },
        "note": "distribution_only_no_auto_production_change",
    }


def audit_trades(*, limit: int = 50, client: DemoWriteClient | None = None) -> dict[str, Any]:
    load_demo_env(resolve_demo_env_path())
    cli = client or DemoWriteClient()
    if not cli.api_key:
        return {
            "ok": False,
            "error": "BYBIT_DEMO_API_KEY missing",
            "hint": "Set BYBIT_DEMO_API_KEY/BYBIT_DEMO_API_SECRET or NEXUS_DEMO_ENV_FILE",
        }

    closed: list[dict[str, Any]] = cli.list_closed_pnl_paginated(
        limit=50,
        max_pages=max(1, (limit * 3 + 49) // 50),
    )

    trips = _pair_round_trips(closed)[:limit]
    last_closure = load_last_trade_closure(closure_path(campaign_root()))

    trades_out: list[dict[str, Any]] = []
    wins = losses = 0
    gross_pnl = fees_total = net_pnl = 0.0
    win_vals: list[float] = []
    loss_vals: list[float] = []
    fee_dom = stop_loss = 0
    symbols: Counter[str] = Counter()
    setups: Counter[str] = Counter()
    exit_reasons: Counter[str] = Counter()
    long_net = short_net = 0.0
    long_n = short_n = 0
    root_agg: Counter[str] = Counter()
    root_loss: dict[str, float] = defaultdict(float)
    same_setup_repeats = 0
    prev_setup: str | None = None
    prev_symbol: str | None = None
    hold_secs: list[float] = []
    under_10 = under_30 = under_60 = 0
    gross_pos_net_neg = 0
    fee_drags: list[float] = []
    symbol_counts: Counter[str] = Counter()
    symbol_entry_times: dict[str, list[int]] = defaultdict(list)
    consecutive_symbol_runs = 0
    funding_total = 0.0
    confirmed: Counter[str] = Counter()
    supported: Counter[str] = Counter()
    hypothesized: Counter[str] = Counter()
    undetermined_count = 0

    for row in trips:
        sym = row.get("symbol")
        side_raw = str(row.get("side") or "")
        side = "LONG" if side_raw.upper() in {"BUY", "LONG"} else "SHORT" if side_raw.upper() in {"SELL", "SHORT"} else side_raw or None
        entry_ts = int(row.get("createdTime") or 0)
        exit_ts = int(row.get("updatedTime") or row.get("createdTime") or 0)
        hold_sec = (exit_ts - entry_ts) / 1000.0 if exit_ts and entry_ts else None
        entry_px = _f(row.get("avgEntryPrice"))
        exit_px = _f(row.get("avgExitPrice"))
        qty = _f(row.get("qty") or row.get("closedSize"))
        notional = (entry_px * qty) if entry_px and qty else None
        open_fee = _f(row.get("openFee"))
        close_fee = _f(row.get("closeFee"))
        funding = _f(row.get("fundingFee"))
        closed_pnl = _f(row.get("closedPnl"))
        ea = build_exact_pnl_breakdown(
            exchange_closed_pnl=row.get("closedPnl"),
            open_fee=open_fee,
            close_fee=close_fee,
            funding=funding,
            side=str(side or "LONG"),
            qty=qty,
            entry_price=entry_px,
            exit_price=exit_px,
            cum_entry_value=row.get("cumEntryValue"),
            cum_exit_value=row.get("cumExitValue"),
            close_side=side_raw,
        )
        net = _f(ea.get("calculated_net_pnl") or ea.get("net_realized"))
        gross_price = _f(ea.get("gross_price_pnl"))
        setup_sig = build_setup_signature(symbol=str(sym or ""), side=str(side or "LONG"))
        if prev_setup == setup_sig:
            same_setup_repeats += 1
        prev_setup = setup_sig

        exit_reason = None
        acct_complete = None
        wallet_recon = None
        reflection_created = None
        mistake_sig = None
        mfe = mae = None
        process_class = None
        if isinstance(last_closure, dict) and str(last_closure.get("symbol")) == str(sym):
            exit_reason = last_closure.get("exit_reason")
            acct_complete = last_closure.get("ACCOUNTING_COMPLETE")
            wallet_recon = (last_closure.get("wallet_reconciliation") or {}).get("WALLET_RECONCILIATION_PASS")
            reflection_created = last_closure.get("Reflection_created")
            mistake_sig = last_closure.get("mistake_signature")
            path = (last_closure.get("path_excursion") or last_closure.get("MFE") is not None and last_closure) or {}
            if isinstance(path, dict):
                mfe = path.get("mfe_usdt") if "mfe_usdt" in path else last_closure.get("MFE")
                mae = path.get("mae_usdt") if "mae_usdt" in path else last_closure.get("MAE")
            process_class = last_closure.get("process_class")

        row["_exit_reason"] = exit_reason
        row["_hold_sec"] = hold_sec
        row["_gross_price_pnl"] = gross_price
        row["_accounting_complete"] = acct_complete
        row["_same_symbol_consecutive"] = prev_symbol == sym
        if prev_symbol == sym:
            consecutive_symbol_runs += 1
        prev_symbol = str(sym) if sym else prev_symbol
        if hold_sec is not None:
            hold_secs.append(hold_sec)
            if hold_sec < 10:
                under_10 += 1
            if hold_sec < 30:
                under_30 += 1
            if hold_sec < 60:
                under_60 += 1
        if sym:
            symbol_counts[str(sym)] += 1
            if entry_ts:
                symbol_entry_times[str(sym)].append(entry_ts)
        if gross_price is not None and gross_price > 0 and net is not None and net < 0:
            gross_pos_net_neg += 1
        ft = abs(open_fee or 0) + abs(close_fee or 0)
        if ft > 0:
            fee_drags.append(ft)
        if funding is not None:
            funding_total += abs(funding)
        if net is not None:
            net_pnl += net
            if net >= 0:
                wins += 1
                win_vals.append(net)
            else:
                losses += 1
                loss_vals.append(net)
            if side == "LONG":
                long_net += net
                long_n += 1
            elif side == "SHORT":
                short_net += net
                short_n += 1
        if gross_price is not None:
            gross_pnl += gross_price
        ft = abs(open_fee or 0) + abs(close_fee or 0)
        fees_total += ft
        if net is not None and net < 0 and ft >= abs(net) * 0.5:
            fee_dom += 1
        if exit_reason and "STOP" in str(exit_reason).upper():
            stop_loss += 1
        if sym:
            symbols[str(sym)] += min(0.0, net or 0.0)
        setups[setup_sig] += 1
        if exit_reason:
            exit_reasons[str(exit_reason)] += 1

        for tag in _classify_loss_root_causes(row, net=net, hold_sec=hold_sec):
            cause = tag["cause"]
            lvl = tag["evidence_level"]
            root_agg[cause] += 1
            if net is not None and net < 0:
                root_loss[cause] += net
            if lvl == "CONFIRMED":
                confirmed[cause] += 1
            elif lvl == "SUPPORTED":
                supported[cause] += 1
            elif lvl == "HYPOTHESIS":
                hypothesized[cause] += 1
            elif cause == "UNDETERMINED":
                undetermined_count += 1

        trades_out.append(
            {
                "trade_id": row.get("orderId"),
                "order_id": row.get("orderId"),
                "symbol": sym,
                "side": side,
                "entry_time": entry_ts or None,
                "exit_time": exit_ts or None,
                "hold_sec": hold_sec,
                "entry_price": entry_px,
                "exit_price": exit_px,
                "notional": notional,
                "exit_reason": exit_reason,
                "gross_price_pnl": gross_price,
                "open_fee": open_fee,
                "close_fee": close_fee,
                "funding": funding,
                "net_realized": net,
                "MFE": mfe,
                "MAE": mae,
                "strategy_family": STRATEGY_FAMILY,
                "regime": REGIME,
                "setup_signature": setup_sig,
                "process_class": process_class,
                "ACCOUNTING_COMPLETE": acct_complete,
                "wallet_reconciliation": wallet_recon,
                "Reflection_created": reflection_created,
                "mistake_signature": mistake_sig,
                "root_causes": _classify_loss_root_causes(row, net=net, hold_sec=hold_sec),
            }
        )

    total = len(trades_out)
    win_rate = (wins / total) if total else None
    avg_win = (sum(win_vals) / len(win_vals)) if win_vals else None
    avg_loss = (sum(loss_vals) / len(loss_vals)) if loss_vals else None
    med_win = _median(win_vals)
    med_loss = _median([abs(x) for x in loss_vals])
    gross_wins = sum(x for x in win_vals if x > 0)
    gross_losses = abs(sum(x for x in loss_vals if x < 0))
    profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else None
    expectancy = (net_pnl / total) if total else None
    loss_total = abs(sum(loss_vals)) if loss_vals else 0.0
    med_hold = _median(hold_secs)
    p25_hold = _percentile(hold_secs, 0.25)
    p75_hold = _percentile(hold_secs, 0.75)
    gross_abs = abs(gross_pnl) if gross_pnl else 0.0
    fees_pct_gross = (fees_total / gross_abs * 100.0) if gross_abs > 0 else None
    edge_cost_ratios = []
    for t in trades_out:
        g = _f(t.get("gross_price_pnl"))
        n = _f(t.get("net_realized"))
        f = abs(_f(t.get("open_fee")) or 0) + abs(_f(t.get("close_fee")) or 0)
        if g and f:
            edge_cost_ratios.append(abs(g) / f)
    churn = _churn_risk_distribution(
        trades=trades_out,
        symbol_concentration=dict(symbol_counts),
        median_hold=med_hold,
        under_30s=under_30,
        fee_drag_median=_median(fee_drags),
    )
    reentry_gaps: list[float] = []
    for sym, times in symbol_entry_times.items():
        times_sorted = sorted(times)
        for i in range(1, len(times_sorted)):
            reentry_gaps.append((times_sorted[i] - times_sorted[i - 1]) / 1000.0)
    root_summary = []
    for tag, cnt in root_agg.most_common():
        nl = abs(root_loss.get(tag, 0.0))
        root_summary.append(
            {
                "root_cause": tag,
                "count": cnt,
                "net_loss": root_loss.get(tag, 0.0),
                "percentage_of_losses": (nl / loss_total * 100.0) if loss_total else None,
            }
        )

    return {
        "ok": True,
        "source": "bybit_demo_closed_pnl",
        "limit": limit,
        "trades": trades_out,
        "summary": {
            "trade_count": total,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "gross_pnl": gross_pnl,
            "fees_total": fees_total,
            "funding_total": funding_total,
            "net_pnl": net_pnl,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "median_win": med_win,
            "median_loss": med_loss,
            "profit_factor": profit_factor,
            "expectancy_per_trade": expectancy,
            "median_hold_sec": med_hold,
            "p25_hold_sec": p25_hold,
            "p75_hold_sec": p75_hold,
            "round_trips_under_10_sec": under_10,
            "round_trips_under_30_sec": under_30,
            "round_trips_under_60_sec": under_60,
            "fees_as_pct_of_gross_abs_pnl": fees_pct_gross,
            "symbol_concentration": dict(symbol_counts.most_common(10)),
            "top_symbols_by_trade_count": symbol_counts.most_common(10),
            "same_symbol_consecutive_runs": consecutive_symbol_runs,
            "same_setup_repeat_count": same_setup_repeats,
            "LONG": {"count": long_n, "net_pnl": long_net},
            "SHORT": {"count": short_n, "net_pnl": short_net},
            "gross_positive_net_negative_count": gross_pos_net_neg,
            "edge_to_cost_ratio_median": _median(edge_cost_ratios),
            "fee_drag_per_round_trip_median": _median(fee_drags),
            "trades_per_symbol_per_hour": {
                sym: round(cnt / max(0.01, (max(times) - min(times)) / 3_600_000), 4)
                for sym, times in symbol_entry_times.items()
                if len(times) >= 2 and max(times) > min(times)
            },
            "median_time_between_same_symbol_entries_sec": _median(reentry_gaps),
            "CHURN_RISK": churn,
            "root_causes": root_summary,
            "confirmed_loss_causes": dict(confirmed),
            "supported_loss_causes": dict(supported),
            "hypothesized_loss_causes": dict(hypothesized),
            "undetermined_loss_count": undetermined_count,
        },
    }


def main() -> int:
    limit = int(os.environ.get("NEXUS_AUDIT_TRADE_LIMIT", "50"))
    out = audit_trades(limit=limit)
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
