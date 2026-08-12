"""Lifecycle purpose separation — EXECUTION_CANARY vs RESEARCH_PNL_TRADE.

EXECUTION_CANARY proves transport/recon only and MUST NOT enter strategy
wins/losses/alpha/profitability counters.
RESEARCH_PNL_TRADE is strategy-driven entry/hold/management/exit.
"""
from __future__ import annotations

from typing import Any

LIFECYCLE_PURPOSE_EXECUTION_CANARY = "EXECUTION_CANARY"
LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE = "RESEARCH_PNL_TRADE"

ENTRY_EXIT_AUDIT_CLASSES = (
    "CANARY_FORCED_CLOSE",
    "IMMEDIATE_TIME_EXIT",
    "MANAGEMENT_BUG",
    "TRIGGER_RESET",
    "STOP_TOO_TIGHT",
    "NO_HOLD_POLICY",
    "OTHER",
)


def is_pnl_bearing(purpose: str | None) -> bool:
    return str(purpose or "") == LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE


def is_execution_canary(purpose: str | None) -> bool:
    return str(purpose or "") == LIFECYCLE_PURPOSE_EXECUTION_CANARY


def audit_entry_exit_proximity(
    *,
    entry_price: float,
    exit_price: float,
    hold_sec: float | None,
    exit_reason: str | None,
    lifecycle_purpose: str | None,
    stop_pct: float | None = None,
    auto_close_immediate: bool = False,
    max_hold_sec: float | None = None,
) -> dict[str, Any]:
    """Classify why entry≈exit — do not invent wins; diagnose process."""
    entry = float(entry_price or 0.0)
    exit_ = float(exit_price or 0.0)
    move_pct = abs(exit_ - entry) / entry * 100.0 if entry > 0 else 0.0
    hold = float(hold_sec) if hold_sec is not None else None
    reason = str(exit_reason or "").lower()
    purpose = str(lifecycle_purpose or "")

    clazz = "OTHER"
    detail = "unclassified"

    if purpose == LIFECYCLE_PURPOSE_EXECUTION_CANARY or auto_close_immediate:
        clazz = "CANARY_FORCED_CLOSE"
        detail = "execution_canary_or_forced_transport_close"
    elif hold is not None and hold < 5.0 and ("max_hold" in reason or "reduce_only" in reason):
        clazz = "IMMEDIATE_TIME_EXIT"
        detail = f"hold_sec={hold:.3f}<5 with time/reduce close"
    elif hold is not None and hold < 15.0 and max_hold_sec is not None and float(max_hold_sec) <= 60:
        clazz = "NO_HOLD_POLICY"
        detail = f"max_hold_sec={max_hold_sec} produced short hold={hold:.3f}"
    elif stop_pct is not None and float(stop_pct) < 0.15 and move_pct < 0.05:
        clazz = "STOP_TOO_TIGHT"
        detail = f"stop_pct={stop_pct}"
    elif "trigger" in reason or "reset" in reason:
        clazz = "TRIGGER_RESET"
        detail = reason
    elif "bug" in reason or "management" in reason:
        clazz = "MANAGEMENT_BUG"
        detail = reason
    elif move_pct < 0.05 and hold is not None and hold < 30.0:
        clazz = "IMMEDIATE_TIME_EXIT"
        detail = f"near_flat move_pct={move_pct:.4f} hold={hold:.3f}"
    else:
        clazz = "OTHER"
        detail = f"move_pct={move_pct:.4f} hold={hold}"

    return {
        "schema": "v18_2_24_entry_exit_proximity_audit_v1",
        "entry_price": entry,
        "exit_price": exit_,
        "move_pct": move_pct,
        "hold_sec": hold,
        "exit_reason": exit_reason,
        "lifecycle_purpose": purpose or None,
        "class": clazz,
        "known_classes": list(ENTRY_EXIT_AUDIT_CLASSES),
        "detail": detail,
        "economically_meaningless": move_pct < 0.05 and (hold is None or hold < 60.0),
    }


def separate_counters(lifecycles: list[dict[str, Any]]) -> dict[str, Any]:
    """Split canaries from PnL research trades for metrics."""
    canaries: list[dict[str, Any]] = []
    pnl_trades: list[dict[str, Any]] = []
    for life in lifecycles:
        purpose = life.get("lifecycle_purpose") or life.get("purpose")
        if is_execution_canary(purpose):
            canaries.append(life)
        elif is_pnl_bearing(purpose):
            pnl_trades.append(life)
        else:
            # Legacy unlabeled real lifecycles treated as canary-like (not PnL research)
            canaries.append({**life, "lifecycle_purpose_inferred": LIFECYCLE_PURPOSE_EXECUTION_CANARY})

    def _net(L: dict[str, Any]) -> float:
        wr = L.get("wallet_reconciliation") or {}
        closed = L.get("exchange_closed_pnl") or {}
        v = closed.get("closedPnl")
        if v is None:
            v = (L.get("pnl_provenance_audit") or {}).get("exchange_closed_pnl")
        if v is None:
            v = wr.get("exchange_realized_pnl")
        try:
            return float(v or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _fees(L: dict[str, Any]) -> float:
        wr = L.get("wallet_reconciliation") or {}
        try:
            return abs(float(wr.get("fees") or wr.get("fees_abs") or 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _funding(L: dict[str, Any]) -> float:
        wr = L.get("wallet_reconciliation") or {}
        closed = L.get("exchange_closed_pnl") or {}
        try:
            return float(closed.get("fundingFee") or wr.get("funding") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _hold(L: dict[str, Any]) -> float | None:
        v = L.get("hold_sec")
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    wins = [L for L in pnl_trades if _net(L) > 0]
    losses = [L for L in pnl_trades if _net(L) < 0]
    nets = [_net(L) for L in pnl_trades]
    fees = [_fees(L) for L in pnl_trades]
    funds = [_funding(L) for L in pnl_trades]
    holds = [h for h in (_hold(L) for L in pnl_trades) if h is not None]
    win_nets = [_net(L) for L in wins]
    loss_nets = [abs(_net(L)) for L in losses]
    gross = sum(nets)
    fee_sum = sum(fees)
    fund_sum = sum(funds)
    avg_win = sum(win_nets) / len(win_nets) if win_nets else None
    avg_loss = sum(loss_nets) / len(loss_nets) if loss_nets else None
    pf = (sum(win_nets) / sum(loss_nets)) if win_nets and loss_nets and sum(loss_nets) > 0 else None
    process_counts: dict[str, int] = {}
    for L in pnl_trades:
        pc = str(L.get("process_class") or "UNKNOWN")
        process_counts[pc] = process_counts.get(pc, 0) + 1

    return {
        "schema": "v18_2_24_lifecycle_purpose_counters_v1",
        "execution_canaries": {
            "n": len(canaries),
            "counted_in_strategy_wins_losses": False,
            "counted_in_alpha_profitability": False,
            "order_ids": [c.get("bybit_orderId") or c.get("order_id") for c in canaries],
        },
        "pnl_research_trades": {
            "n": len(pnl_trades),
            "wins": len(wins),
            "losses": len(losses),
            "flat": len(pnl_trades) - len(wins) - len(losses),
            "gross_pnl": gross,
            "fees": fee_sum,
            "funding": fund_sum,
            "net_pnl": gross,  # exchange closedPnl already fee-inclusive when recon PASS
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": pf,
            "avg_hold_sec": (sum(holds) / len(holds)) if holds else None,
            "process_class_counts": process_counts,
            "order_ids": [c.get("bybit_orderId") or c.get("order_id") for c in pnl_trades],
        },
        "n_requirement_quality_over_count": True,
        "no_n5_at_expense_of_quality": True,
        "prefer_economically_meaningful": True,
    }
