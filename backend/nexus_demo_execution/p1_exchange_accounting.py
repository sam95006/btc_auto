"""Shared exact-identity Bybit Demo accounting helpers.

Never use newest-row or symbol-only proof as closed-PnL authority.
"""
from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

EXCHANGE_BACKED_PROVENANCE = frozenset(
    {
        "EXCHANGE_REALIZED_PNL",
        "BYBIT_V5_POSITION_CLOSED_PNL",
    }
)
PROVISIONAL_PROVENANCE = frozenset(
    {
        "STRATEGY_OUTCOME_MODEL",
        "INTERNAL_SIMULATION_PNL",
        "MIXED",
        "PENDING",
        "UNAVAILABLE",
        "",
        None,
    }
)
PNL_POLL_INTERVAL_SEC = 2.0
PNL_POLL_TIMEOUT_SEC = 60.0
WINDOW_PAD_MS = 3_600_000


def _d(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def is_exchange_backed_provenance(value: Any) -> bool:
    return str(value or "").strip() in EXCHANGE_BACKED_PROVENANCE


def is_provisional_provenance(value: Any) -> bool:
    text = str(value).strip() if value is not None else ""
    return text not in EXCHANGE_BACKED_PROVENANCE


def realized_pnl_absent(value: Any) -> bool:
    return value in (None, "")


def match_closed_pnl_by_close_order_id(rows: list[dict[str, Any]], close_order_id: str) -> dict[str, Any] | None:
    wanted = str(close_order_id or "")
    if not wanted:
        return None
    for row in rows:
        if str(row.get("orderId") or "") == wanted:
            return row
    return None


def aggregate_executions(rows: list[dict[str, Any]], order_id: str) -> dict[str, Any]:
    wanted = str(order_id or "")
    qty = Decimal("0")
    notional = Decimal("0")
    fee = Decimal("0")
    matched = 0
    for row in rows:
        if str(row.get("orderId") or "") != wanted:
            continue
        matched += 1
        exec_qty = _d(row.get("execQty") or row.get("qty"))
        exec_price = _d(row.get("execPrice") or row.get("price"))
        qty += exec_qty
        notional += exec_qty * exec_price
        fee += abs(_d(row.get("execFee") or row.get("fee")))
    return {
        "qty": qty,
        "vwap": (notional / qty) if qty > 0 else None,
        "fee": fee,
        "count": matched,
    }


def bounded_window_ms(anchor_ms: int | None, *, now_ms: int, pad_ms: int = WINDOW_PAD_MS) -> tuple[int, int]:
    anchor = int(anchor_ms or now_ms)
    start = max(0, anchor - int(pad_ms))
    end = max(start, anchor + int(pad_ms))
    return start, end


def list_executions_for_order(client: Any, *, symbol: str, order_id: str) -> list[dict[str, Any]]:
    if hasattr(client, "list_executions"):
        try:
            return list(client.list_executions(symbol=symbol, limit=100, order_id=order_id) or [])
        except TypeError:
            rows = list(client.list_executions(symbol=symbol, limit=100) or [])
            return [row for row in rows if str(row.get("orderId") or "") == str(order_id)]
    return []


def list_closed_pnl_window(
    client: Any,
    *,
    symbol: str,
    start_time_ms: int,
    end_time_ms: int,
) -> list[dict[str, Any]]:
    if hasattr(client, "list_closed_pnl_paginated"):
        return list(
            client.list_closed_pnl_paginated(
                symbol=symbol,
                limit=100,
                max_pages=10,
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
            )
            or []
        )
    return list(client.list_closed_pnl(symbol=symbol, limit=50) or [])


def poll_exact_closed_pnl(
    client: Any,
    *,
    symbol: str,
    close_order_id: str,
    start_time_ms: int,
    end_time_ms: int,
    sleep: Callable[[float], None] = time.sleep,
    time_fn: Callable[[], float] = time.time,
    interval_sec: float = PNL_POLL_INTERVAL_SEC,
    timeout_sec: float = PNL_POLL_TIMEOUT_SEC,
) -> tuple[dict[str, Any] | None, int]:
    deadline = time_fn() + timeout_sec
    attempts = 0
    while True:
        attempts += 1
        rows = list_closed_pnl_window(
            client,
            symbol=symbol,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        )
        matched = match_closed_pnl_by_close_order_id(rows, close_order_id)
        if matched is not None:
            return matched, attempts
        if time_fn() >= deadline:
            return None, attempts
        sleep(interval_sec)
