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


def _classify_loss_root_causes(row: dict[str, Any], *, net: float | None) -> list[str]:
    if net is None or net >= 0:
        return []
    tags: list[str] = []
    open_fee = abs(_f(row.get("openFee")) or 0.0)
    close_fee = abs(_f(row.get("closeFee")) or 0.0)
    fees = open_fee + close_fee
    closed_pnl = _f(row.get("closedPnl"))
    gross = None
    avg_entry = _f(row.get("avgEntryPrice"))
    avg_exit = _f(row.get("avgExitPrice"))
    side = str(row.get("side") or "").upper()
    qty = _f(row.get("qty") or row.get("closedSize"))
    if avg_entry and avg_exit and qty:
        if side in {"SELL", "SHORT"} or (side == "SELL" and True):
            gross = (avg_entry - avg_exit) * qty
        else:
            gross = (avg_exit - avg_entry) * qty
    if net < 0 and fees > 0 and (closed_pnl is not None and abs(closed_pnl) <= fees * 1.05):
        tags.append("COST_DOMINATED")
    elif net < 0 and gross is not None and abs(gross) < fees:
        tags.append("COST_DOMINATED")
    if gross is not None and gross < 0:
        tags.append("DIRECTION_WRONG")
    if gross is not None and abs(gross) < fees * 0.25:
        tags.append("NOISE_ENTRY")
    exit_reason = str(row.get("_exit_reason") or "").upper()
    if "STOP" in exit_reason:
        tags.append("STOP_TOO_TIGHT")
    hold = _f(row.get("_hold_sec"))
    if hold is not None and hold < 180:
        tags.append("HORIZON_MISMATCH")
    if not tags:
        tags.append("UNDETERMINED")
    return tags


def _map_aggregate_ab(tags: list[str]) -> dict[str, int]:
    mapping = {
        "A": {"LOW_ACTIVITY", "LIQUIDITY_WEAK", "NOISE_ENTRY"},
        "B": {"DIRECTION_WRONG", "AMBIGUOUS_DIRECTION"},
        "C": {"ENTRY_TOO_EARLY", "ENTRY_TOO_LATE", "FALSE_BREAKOUT"},
        "D": {"STOP_TOO_TIGHT"},
        "E": {"COST_DOMINATED"},
        "F": {"REGIME_MISMATCH"},
        "G": set(),
        "H": {"EXIT_GIVEBACK", "HORIZON_MISMATCH"},
        "I": {"EXCHANGE_ACCOUNTING_INCOMPLETE"},
        "J": {"UNDETERMINED"},
    }
    out: dict[str, int] = {k: 0 for k in mapping}
    for t in tags:
        for k, vals in mapping.items():
            if t in vals:
                out[k] += 1
    return out


def audit_trades(*, limit: int = 20, client: DemoWriteClient | None = None) -> dict[str, Any]:
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

        for tag in _classify_loss_root_causes(row, net=net):
            root_agg[tag] += 1
            if net is not None and net < 0:
                root_loss[tag] += net

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
                "root_causes": _classify_loss_root_causes(row, net=net),
            }
        )

    total = len(trades_out)
    win_rate = (wins / total) if total else None
    avg_win = (sum(win_vals) / len(win_vals)) if win_vals else None
    avg_loss = (sum(loss_vals) / len(loss_vals)) if loss_vals else None
    gross_wins = sum(x for x in win_vals if x > 0)
    gross_losses = abs(sum(x for x in loss_vals if x < 0))
    profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else None
    expectancy = (net_pnl / total) if total else None
    loss_total = abs(sum(loss_vals)) if loss_vals else 0.0
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
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "gross_pnl": gross_pnl,
            "fees_total": fees_total,
            "net_pnl": net_pnl,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "fee_dominated_losses": fee_dom,
            "stop_loss_count": stop_loss,
            "same_symbol_repeat_count": sum(1 for c in symbols.values() if c < -1),
            "same_setup_repeat_count": same_setup_repeats,
            "LONG": {"count": long_n, "net_pnl": long_net},
            "SHORT": {"count": short_n, "net_pnl": short_net},
            "top_losing_symbols": symbols.most_common(5),
            "top_losing_setup_signatures": setups.most_common(5),
            "top_exit_reasons": exit_reasons.most_common(),
            "root_causes": root_summary,
            "aggregate_ab": _map_aggregate_ab(list(root_agg.keys())),
        },
    }


def main() -> int:
    limit = int(os.environ.get("NEXUS_AUDIT_TRADE_LIMIT", "20"))
    out = audit_trades(limit=limit)
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
