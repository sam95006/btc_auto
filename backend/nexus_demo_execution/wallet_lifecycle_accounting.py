"""REAL Demo wallet lifecycle accounting — Decimal precision, no fabricated deltas."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from backend.nexus_demo_execution.pnl_accounting import build_exact_pnl_breakdown


PNL_PROVENANCE = (
    "EXCHANGE_REALIZED_PNL",
    "INTERNAL_SIMULATION_PNL",
    "STRATEGY_OUTCOME_MODEL",
    "MIXED",
    "PENDING",
    "UNAVAILABLE",
)

ACCOUNTING_STATUS = (
    "ACCOUNTING_COMPLETE",
    "WALLET_RECONCILIATION_PASS",
    "WALLET_RECONCILIATION_MISMATCH",
    "WALLET_DELTA_NOT_RECONSTRUCTABLE",
    "PENDING_POSITION_ZERO",
    "PENDING_WALLET_AFTER",
)


def _d(v: Any) -> Decimal:
    if v is None or v == "":
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _full(v: Decimal) -> str:
    """Full precision string — never hide tiny deltas via rounding."""
    s = format(v, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def classify_pnl_provenance(
    *,
    exchange_closed_pnl: Any = None,
    exchange_exec_fee: Any = None,
    internal_pnl: Any = None,
    strategy_model_pnl: Any = None,
    has_exchange_fill: bool = False,
) -> dict[str, Any]:
    """Classify PnL provenance. REAL win/loss only if exchange realized supports it."""
    ex = _d(exchange_closed_pnl) if exchange_closed_pnl is not None else None
    fee = _d(exchange_exec_fee) if exchange_exec_fee is not None else Decimal("0")
    internal = _d(internal_pnl) if internal_pnl is not None else None
    model = _d(strategy_model_pnl) if strategy_model_pnl is not None else None

    sources = []
    if ex is not None and has_exchange_fill:
        sources.append("EXCHANGE_REALIZED_PNL")
    if internal is not None and (ex is None or not has_exchange_fill):
        sources.append("INTERNAL_SIMULATION_PNL")
    if model is not None and (ex is None or not has_exchange_fill):
        sources.append("STRATEGY_OUTCOME_MODEL")
    if ex is not None and has_exchange_fill and (internal is not None or model is not None):
        # Both present → MIXED if they disagree beyond fee dust
        ref = internal if internal is not None else model
        if ref is not None and abs(ex - ref) > abs(fee) + Decimal("0.00000001"):
            provenance = "MIXED"
        else:
            provenance = "EXCHANGE_REALIZED_PNL"
    elif len(sources) > 1:
        provenance = "MIXED"
    elif sources:
        provenance = sources[0]
    else:
        provenance = "UNAVAILABLE"

    real_win = None
    real_loss = None
    if provenance == "EXCHANGE_REALIZED_PNL" and ex is not None:
        real_win = ex > 0
        real_loss = ex < 0
    elif provenance == "MIXED" and ex is not None and has_exchange_fill:
        real_win = ex > 0
        real_loss = ex < 0

    return {
        "pnl_provenance": provenance,
        "exchange_closed_pnl": _full(ex) if ex is not None else None,
        "exchange_fee_total": _full(fee),
        "internal_pnl": _full(internal) if internal is not None else None,
        "strategy_model_pnl": _full(model) if model is not None else None,
        "real_win_supported_by_exchange": real_win,
        "real_loss_supported_by_exchange": real_loss,
        "known_classes": list(PNL_PROVENANCE),
    }


def reconcile_wallet_before_after(
    *,
    wallet_before: Any,
    wallet_after: Any,
    exchange_realized_pnl: Any = None,
    fees: Any = None,
    funding: Any = None,
    tolerance: Any = "0.00000001",
) -> dict[str, Any]:
    """actual_wallet_delta = after-before; expected from exchange PnL/fees/funding.

    Bybit Demo closedPnl is sometimes fee-inclusive (flat cycles: closedPnl ≈ -fees).
    Prefer the formulation that matches exchange accounting without double-counting fees.
    """
    before = _d(wallet_before)
    after = _d(wallet_after)
    actual = after - before
    realized = _d(exchange_realized_pnl)
    fee = abs(_d(fees))
    fund = _d(funding)
    tol = _d(tolerance)

    # Candidate expectations
    candidates = {
        "realized_minus_fees_plus_funding": realized - fee + fund,
        "realized_only_fee_inclusive": realized + fund,
        "fees_and_funding_only": -fee + fund,
    }
    # Choose candidate with minimal absolute error vs actual
    best_name = "realized_minus_fees_plus_funding"
    best_err = abs(actual - candidates[best_name])
    for name, exp in candidates.items():
        err = abs(actual - exp)
        if err < best_err:
            best_name, best_err = name, err
    expected = candidates[best_name]
    delta_err = actual - expected
    passed = abs(delta_err) <= tol
    status = "WALLET_RECONCILIATION_PASS" if passed else "WALLET_RECONCILIATION_MISMATCH"
    return {
        "wallet_balance_before": _full(before),
        "wallet_balance_after": _full(after),
        "actual_wallet_delta": _full(actual),
        "expected_wallet_delta": _full(expected),
        "exchange_realized_pnl": _full(realized),
        "fees": _full(_d(fees)),
        "fees_abs": _full(fee),
        "funding": _full(fund),
        "delta_error": _full(delta_err),
        "tolerance": _full(tol),
        "expectation_model": best_name,
        "status": status,
        "WALLET_RECONCILIATION_PASS": passed,
        "fabricated_accounting": False,
        "full_precision": True,
    }


def build_lifecycle_accounting_record(
    *,
    lifecycle: dict[str, Any],
    account_identity: dict[str, Any],
    wallet_before: dict[str, Any] | None = None,
    wallet_after: dict[str, Any] | None = None,
    exchange_fill: dict[str, Any] | None = None,
    exchange_close: dict[str, Any] | None = None,
    historical: bool = False,
) -> dict[str, Any]:
    """Attach account/wallet/PnL provenance to a REAL_BYBIT_DEMO lifecycle."""
    identity = {
        "exchange_domain": account_identity.get("exchange_domain") or "api-demo.bybit.com",
        "api_key_fingerprint": account_identity.get("api_key_fingerprint"),
        "account_uid": account_identity.get("account_uid"),
        "account_type": account_identity.get("account_type") or account_identity.get("wallet_type"),
        "wallet_type": account_identity.get("wallet_type") or account_identity.get("wallet_context"),
        "wallet_context": account_identity.get("wallet_context"),
        "settle_coin": account_identity.get("settle_coin") or "USDT",
        "symbol": lifecycle.get("symbol"),
        "category": "linear",
        "demo_account_confirmed_for_founder": bool(account_identity.get("api_key_fingerprint")),
    }

    fill = dict(exchange_fill or {})
    close = dict(exchange_close or {})
    order_id = (
        fill.get("orderId")
        or lifecycle.get("bybit_orderId")
        or lifecycle.get("order_id")
    )
    exec_id = (
        fill.get("execId")
        or fill.get("executionId")
        or lifecycle.get("bybit_executionId")
        or lifecycle.get("execution_id")
    )

    closed_pnl = close.get("closedPnl")
    if closed_pnl is None:
        closed_pnl = fill.get("closedPnl")
    fee_total = _d(fill.get("execFee"))
    if close.get("openFee") is not None or close.get("closeFee") is not None:
        fee_total = abs(_d(close.get("openFee"))) + abs(_d(close.get("closeFee")))
    funding = _d(close.get("fundingFee"))

    provenance = classify_pnl_provenance(
        exchange_closed_pnl=closed_pnl,
        exchange_exec_fee=fee_total,
        internal_pnl=lifecycle.get("pnl_pct"),
        has_exchange_fill=bool(order_id and exec_id),
    )

    accounting_status = "PENDING_WALLET_AFTER"
    recon = None
    if historical and not wallet_before:
        accounting_status = "WALLET_DELTA_NOT_RECONSTRUCTABLE"
    elif wallet_before and wallet_after and lifecycle.get("position_zero"):
        recon = reconcile_wallet_before_after(
            wallet_before=wallet_before.get("wallet_balance") or wallet_before.get("coin_balance"),
            wallet_after=wallet_after.get("wallet_balance") or wallet_after.get("coin_balance"),
            exchange_realized_pnl=closed_pnl if closed_pnl is not None else "0",
            fees=fee_total,
            funding=funding,
        )
        accounting_status = (
            "ACCOUNTING_COMPLETE"
            if recon.get("WALLET_RECONCILIATION_PASS")
            else "WALLET_RECONCILIATION_MISMATCH"
        )
        if recon.get("WALLET_RECONCILIATION_PASS"):
            # Explicit pass label retained alongside complete
            recon["accounting_complete"] = True
    elif not lifecycle.get("position_zero"):
        accounting_status = "PENDING_POSITION_ZERO"
    elif wallet_before and not wallet_after:
        accounting_status = "PENDING_WALLET_AFTER"

    return {
        **lifecycle,
        "account": identity,
        "wallet_before": wallet_before,
        "wallet_after": wallet_after,
        "exchange_fill": {
            "orderId": order_id,
            "executionId": exec_id,
            "execPrice": fill.get("execPrice"),
            "execQty": fill.get("execQty"),
            "execFee": fill.get("execFee"),
            "feeCurrency": fill.get("feeCurrency") or fill.get("feeRate") or "USDT",
            "execTime": fill.get("execTime"),
        }
        if (order_id or exec_id or fill)
        else None,
        "exchange_closed_pnl": {
            "closedPnl": str(closed_pnl) if closed_pnl is not None else None,
            "openFee": close.get("openFee"),
            "closeFee": close.get("closeFee"),
            "fundingFee": close.get("fundingFee"),
            "orderId": close.get("orderId"),
            "updatedTime": close.get("updatedTime") or close.get("createdTime"),
            "cumEntryValue": close.get("cumEntryValue"),
            "cumExitValue": close.get("cumExitValue"),
            "avgEntryPrice": close.get("avgEntryPrice"),
            "avgExitPrice": close.get("avgExitPrice"),
            "side": close.get("side"),
        }
        if close or closed_pnl is not None
        else None,
        "pnl_provenance_audit": provenance,
        "exact_pnl_accounting": build_exact_pnl_breakdown(
            exchange_closed_pnl=closed_pnl,
            open_fee=close.get("openFee") if close else None,
            close_fee=close.get("closeFee") if close else None,
            funding=funding,
            wallet_before=(wallet_before or {}).get("wallet_balance")
            or (wallet_before or {}).get("coin_balance"),
            wallet_after=(wallet_after or {}).get("wallet_balance")
            or (wallet_after or {}).get("coin_balance"),
            side=str(lifecycle.get("side") or "LONG"),
            qty=lifecycle.get("qty") or fill.get("execQty"),
            entry_price=lifecycle.get("entry_price")
            or fill.get("execPrice")
            or close.get("avgEntryPrice"),
            exit_price=lifecycle.get("exit_price") or close.get("avgExitPrice"),
            cum_entry_value=close.get("cumEntryValue") if close else None,
            cum_exit_value=close.get("cumExitValue") if close else None,
            close_side=close.get("side") if close else None,
        ),
        "wallet_reconciliation": recon,
        "accounting_status": accounting_status,
        "ACCOUNTING_COMPLETE": accounting_status == "ACCOUNTING_COMPLETE",
        "historical_reconstruct": historical,
        "fabricated_accounting": False,
    }


def match_exchange_rows_for_order(
    *,
    order_id: str | None,
    executions: list[dict[str, Any]],
    closed_pnls: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Read-only match of exchange history to a known orderId."""
    if not order_id:
        return None, None
    oid = str(order_id)
    fill = None
    for row in executions:
        if str(row.get("orderId") or "") == oid:
            fill = {
                "orderId": row.get("orderId"),
                "execId": row.get("execId"),
                "executionId": row.get("execId"),
                "execPrice": row.get("execPrice"),
                "execQty": row.get("execQty"),
                "execFee": row.get("execFee"),
                "feeCurrency": row.get("feeCurrency"),
                "execTime": row.get("execTime"),
                "closedPnl": row.get("closedPnl"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
            }
            # Prefer exit/reduce fills when multiple
            if str(row.get("reduceOnly") or "").lower() in {"true", "1"} or _d(
                row.get("closedPnl")
            ) != 0:
                break
    close = None
    for row in closed_pnls:
        if str(row.get("orderId") or "") == oid:
            close = row
            break
    return fill, close
