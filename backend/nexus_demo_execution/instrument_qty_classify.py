"""Classify DemoWriteError / instrument failures for observability."""
from __future__ import annotations

from typing import Any


def classify_instrument_qty_error(code: str, detail: str = "") -> str:
    c = (code or "").lower()
    d = (detail or "").lower()
    if "instrument_missing" in c or "not found" in d:
        return "instrument_missing"
    if "status" in c or "status" in d or "not_trading" in c:
        return "instrument_status_invalid"
    if "qty_below_min" in c or "min_order_qty" in c:
        return "min_order_qty"
    if "qty_step" in c or "rounding" in c:
        return "qty_step_rounding"
    if "notional_below_min" in c or "min_notional" in c:
        return "min_notional"
    if "tick" in c:
        return "price_tick"
    if "leverage" in c:
        return "leverage_not_supported"
    if "mode" in c or "position_idx" in c:
        return "account_mode_conflict"
    if "reader" in c or "timeout" in c or "http" in c:
        return "reader_failure"
    if "qty_invalid" in c:
        # Usually floor-to-zero after step rounding under high price / low margin.
        return "qty_step_rounding"
    return "other"


def classify_from_exc(exc: Any) -> str:
    code = str(getattr(exc, "code", "") or type(exc).__name__)
    detail = str(getattr(exc, "detail", "") or exc)
    return classify_instrument_qty_error(code, detail)
