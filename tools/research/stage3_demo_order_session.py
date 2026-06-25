"""Stage 3 C+2 controlled Bybit demo-order micro session with balance reconciliation."""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from tools.research.bybit_demo_client import (
    DEFAULT_CATEGORY,
    DEFAULT_MAX_HOLD_MINUTES,
    DEFAULT_STOP_LOSS_MAX_USD,
    DEFAULT_SYMBOL,
    MAX_LEVERAGE,
    MAX_MARGIN_USD,
    BybitDemoClient,
    OrderIntent,
)
from tools.research.bybit_demo_learning_common import utc_now_iso, write_json
from tools.research.stage3_learning_loop import Stage3LearningLoop, append_jsonl, build_balance_reconciliation


def _f(raw: Any) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _decide_side(ticker: Dict[str, Any]) -> str:
    last = float(ticker.get("lastPrice") or 0)
    prev = float(ticker.get("prevPrice24h") or last)
    return "BUY" if last >= prev else "SELL"


def _stop_price(entry: float, qty: float, side: str, stop_loss_max_usd: float) -> float:
    delta = stop_loss_max_usd / max(qty, 1e-9)
    if side.upper() in {"BUY", "LONG"}:
        return max(0.01, entry - delta)
    return entry + delta


def run_demo_order_micro_session(
    *,
    loop: Stage3LearningLoop,
    client: BybitDemoClient,
    snapshot: Dict[str, Any],
    max_orders: int = 1,
    max_hold_minutes: int = DEFAULT_MAX_HOLD_MINUTES,
    stop_loss_max_usd: float = DEFAULT_STOP_LOSS_MAX_USD,
    margin_usd: float = MAX_MARGIN_USD,
    leverage: int = MAX_LEVERAGE,
    poll_interval_seconds: float = 15.0,
    duration_minutes: float = 10.0,
) -> Dict[str, Any]:
    regime = "phase_c_micro_session"
    failure_reason = "controlled_demo_order"
    conf_before = loop.state.confidence
    size_before = loop.state.position_size
    margin_usd = min(margin_usd, MAX_MARGIN_USD, float(snapshot.get("max_allowed_margin") or MAX_MARGIN_USD))
    leverage = min(leverage, MAX_LEVERAGE)
    max_hold_seconds = max_hold_minutes * 60

    ticker = client.fetch_ticker(DEFAULT_SYMBOL)
    entry_price = float(ticker.get("lastPrice") or 0)
    side = _decide_side(ticker)
    notional = margin_usd * leverage
    qty = notional / max(entry_price, 1e-9)
    stop = _stop_price(entry_price, qty, side, stop_loss_max_usd)

    decision_id = str(uuid.uuid4())
    decision = {
        "decision_id": decision_id,
        "scenario": "phase_c_demo_order",
        "symbol": DEFAULT_SYMBOL,
        "side": side,
        "regime": regime,
        "failure_reason": failure_reason,
        "action": "demo_order",
        "confidence": conf_before,
        "position_size": size_before,
        "margin_usd": margin_usd,
        "leverage": leverage,
        "last_price": entry_price,
        "balance_snapshot_id": snapshot.get("snapshot_id"),
        "account_total_equity": snapshot.get("total_equity"),
        "account_available_balance": snapshot.get("available_balance"),
        "account_wallet_balance": snapshot.get("wallet_balance"),
        "balance_read_ok": snapshot.get("balance_read_ok"),
        "recorded_at_utc": utc_now_iso(),
    }
    append_jsonl(loop.path("decisions.jsonl"), decision)

    open_before = client.count_open_positions()
    if open_before > 0:
        raise RuntimeError("existing_open_positions_before_order")

    intent = OrderIntent(
        symbol=DEFAULT_SYMBOL,
        side=side,
        qty=qty,
        price=entry_price,
        stop_loss=stop,
        max_hold_seconds=max_hold_seconds,
        leverage=leverage,
        margin_usd=margin_usd,
    )
    order = client.place_demo_order(intent)
    signal_id = f"sig-c1-{uuid.uuid4().hex[:8]}"
    order_row = {
        **order,
        "decision_id": decision_id,
        "signal_id": signal_id,
        "max_hold_minutes": max_hold_minutes,
        "stop_loss_max_usd": stop_loss_max_usd,
        "balance_snapshot_id": snapshot.get("snapshot_id"),
        "recorded_at_utc": utc_now_iso(),
    }
    append_jsonl(loop.path("orders.jsonl"), order_row)

    session_started = time.time()
    deadline = min(session_started + duration_minutes * 60.0, session_started + max_hold_seconds + 30)
    position_opened = True
    exit_reason = "open"
    exit_price = entry_price
    close_pnl = 0.0
    close_info: Dict[str, Any] = {}

    while time.time() < deadline:
        append_jsonl(loop.path("account_snapshots.jsonl"), client.get_account_balance())
        pos = client.get_primary_open_position()
        if pos is None:
            position_opened = False
            closed = client.get_recent_closed_pnl()
            if closed:
                close_pnl = _f(closed.get("closedPnl"))
                exit_price = _f(closed.get("avgExitPrice") or exit_price)
            exit_reason = "stop_loss_or_exchange_close"
            break
        elapsed = time.time() - session_started
        exit_price = float(pos.get("markPrice") or pos.get("avgPrice") or entry_price)
        close_pnl = float(pos.get("unrealisedPnl") or 0)
        if elapsed >= max_hold_seconds:
            close_info = client.close_demo_position_market()
            exit_reason = "max_hold_timeout"
            time.sleep(2)
            pos_after = client.get_primary_open_position()
            if pos_after is None:
                position_opened = False
            close_pnl = float(close_info.get("unrealised_pnl") or close_pnl)
            break
        time.sleep(poll_interval_seconds)

    if position_opened:
        close_info = client.close_demo_position_market()
        exit_reason = "session_end_force_close"
        position_opened = False
        close_pnl = float(close_info.get("unrealised_pnl") or close_pnl)
        exit_price = float(close_info.get("avg_entry") or exit_price)

    balance_after = client.get_account_balance()
    append_jsonl(loop.path("account_snapshots.jsonl"), balance_after)
    open_after = client.count_open_positions()

    closed_pnl_row = client.get_recent_closed_pnl() or {}
    if closed_pnl_row.get("closedPnl") is not None:
        close_pnl = _f(closed_pnl_row.get("closedPnl"))

    reconciliation = build_balance_reconciliation(
        account_balance_before=snapshot.get("available_balance"),
        account_balance_after=balance_after.get("available_balance"),
        close_pnl=close_pnl,
        closed_pnl_row=closed_pnl_row,
    )

    trade = loop.build_trade_record(
        decision_id=decision_id,
        signal_id=signal_id,
        order_id=order.get("order_id", ""),
        symbol=DEFAULT_SYMBOL,
        side=side,
        entry_price=entry_price,
        exit_price=exit_price,
        close_pnl=close_pnl,
        exit_reason=exit_reason,
        confidence_before=conf_before,
        confidence_after=conf_before,
        position_size_before=size_before,
        position_size_after=size_before,
        reflection_created=False,
        patch_created=False,
        patch_applied_to_next_decision=False,
        repeated_mistake_detected=False,
        repeated_mistake_blocked=False,
    )
    trade["trade_result_id"] = str(uuid.uuid4())
    trade["position_closed"] = open_after == 0
    trade["demo_order_sent"] = True
    trade.update(reconciliation)

    if close_pnl < 0:
        trade = loop.record_loss_reflection_patch(
            decision_id=decision_id,
            trade=trade,
            regime=regime,
            failure_reason=failure_reason,
        )
    else:
        trade["reflection_created"] = False
        trade["patch_created"] = False

    append_jsonl(loop.path("trade_results.jsonl"), trade)

    session_report = {
        "record_type": "stage3_demo_order_session_report",
        "generated_at_utc": utc_now_iso(),
        "phase": "C+2",
        "demo_order_session_started": True,
        "demo_order_sent": True,
        "orders_placed": 1,
        "max_orders": max_orders,
        "order_id": order.get("order_id"),
        "symbol": DEFAULT_SYMBOL,
        "category": DEFAULT_CATEGORY,
        "side": side,
        "margin_usd": margin_usd,
        "leverage": leverage,
        "stop_loss_attached": True,
        "max_hold_minutes": max_hold_minutes,
        "position_opened": True,
        "position_closed": open_after == 0,
        "close_pnl": close_pnl,
        "exit_reason": exit_reason,
        "open_positions_before": open_before,
        "open_positions_after": open_after,
        "decision_id": decision_id,
        "trade_result_id": trade.get("trade_result_id"),
        "reflection_created": trade.get("reflection_created"),
        "patch_created": trade.get("patch_created"),
        "mainnet": False,
        "real_money": False,
        **reconciliation,
    }
    write_json(loop.path("demo_order_session_report.json"), session_report)
    return session_report
