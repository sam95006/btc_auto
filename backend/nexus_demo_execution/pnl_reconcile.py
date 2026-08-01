"""Reconcile fees / net PnL from Bybit closed-PnL / execution history without fabricating zeros."""
from __future__ import annotations

from typing import Any, Callable


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def reconcile_closed_trade_pnl(
    *,
    closed_pnl_row: dict[str, Any] | None,
    execution_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return fee/PnL fields with explicit availability statuses."""
    out: dict[str, Any] = {
        "gross_pnl": None,
        "entry_fee": None,
        "exit_fee": None,
        "total_fees": None,
        "funding": None,
        "slippage": None,
        "net_pnl": None,
        "actual_fees": None,
        "fee_source": None,
        "actual_fees_status": "NOT_FOUND",
        "net_pnl_status": "NOT_AVAILABLE",
        "availability_reason": "",
    }
    row = closed_pnl_row or {}
    if row:
        net = _f(row.get("closedPnl"))
        open_fee = _f(row.get("openFee"))
        close_fee = _f(row.get("closeFee"))
        funding = _f(row.get("fundingFee"))
        if open_fee is not None or close_fee is not None:
            entry = abs(open_fee or 0.0)
            exit_ = abs(close_fee or 0.0)
            total = entry + exit_
            out.update(
                {
                    "entry_fee": entry,
                    "exit_fee": exit_,
                    "total_fees": total,
                    "actual_fees": total,
                    "actual_fees_status": "AVAILABLE",
                    "fee_source": "BYBIT_CLOSED_PNL",
                }
            )
        else:
            out["actual_fees_status"] = "NOT_FOUND"
            out["availability_reason"] = "closed_pnl_missing_fee_fields"
        if funding is not None:
            out["funding"] = funding
        if net is not None:
            out["net_pnl"] = net
            out["net_pnl_status"] = "AVAILABLE"
            # Derive gross when fees known: closedPnl is typically net of fees on Bybit.
            if out["total_fees"] is not None:
                fund = abs(out["funding"] or 0.0)
                out["gross_pnl"] = net + out["total_fees"] + fund
            return out
        out["net_pnl_status"] = "NOT_AVAILABLE"
        out["availability_reason"] = out["availability_reason"] or "closed_pnl_missing_closedPnl"
        return out

    # Fallback: sum execution fee rows if present.
    fees = []
    for ex in execution_rows or []:
        fee = _f(ex.get("execFee") or ex.get("fee"))
        if fee is not None:
            fees.append(abs(fee))
    if fees:
        total = sum(fees)
        out.update(
            {
                "total_fees": total,
                "actual_fees": total,
                "actual_fees_status": "AVAILABLE",
                "fee_source": "BYBIT_EXECUTION_HISTORY",
                "net_pnl_status": "NOT_AVAILABLE",
                "availability_reason": "executions_have_fees_but_no_closed_pnl",
            }
        )
        return out

    out["actual_fees_status"] = "NOT_FOUND"
    out["net_pnl_status"] = "NOT_AVAILABLE"
    out["availability_reason"] = "no_closed_pnl_or_execution_rows"
    return out


def reconcile_via_writer(writer: Any, symbol: str) -> dict[str, Any]:
    """Best-effort fetch closed PnL (+ optional executions) from DemoWriteClient-like writer."""
    closed = None
    executions: list[dict[str, Any]] = []
    try:
        closed = writer.closed_pnl(symbol)
    except Exception as exc:  # noqa: BLE001
        return {
            **reconcile_closed_trade_pnl(closed_pnl_row=None),
            "actual_fees_status": "API_UNSUPPORTED" if "unsupported" in str(exc).lower() else "NOT_FOUND",
            "availability_reason": f"closed_pnl_error:{type(exc).__name__}",
        }
    fetch_exec: Callable[..., Any] | None = getattr(writer, "list_executions", None)
    if callable(fetch_exec):
        try:
            executions = list(fetch_exec(symbol) or [])
        except Exception:
            executions = []
    return reconcile_closed_trade_pnl(closed_pnl_row=closed, execution_rows=executions)
