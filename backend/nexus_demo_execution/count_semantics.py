"""Count / reconciliation semantics — never coerce missing or zero incorrectly."""
from __future__ import annotations

from typing import Any


def count_or_none(value: Any) -> int | None:
    """Return int count, or None if unavailable. Zero is a valid count."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def reconcile_flat(
    position_count: int | None,
    open_order_count: int | None,
) -> str:
    """MATCH only when both counts are known and zero. Never map UNKNOWN→MISMATCH."""
    if position_count is None or open_order_count is None:
        return "UNKNOWN"
    if position_count == 0 and open_order_count == 0:
        return "MATCH"
    return "MISMATCH"


def classify_account_flat(
    position_count: int | None,
    open_order_count: int | None,
) -> str:
    if position_count is None or open_order_count is None:
        return "ACCOUNT_STATE_UNKNOWN"
    if position_count == 0 and open_order_count == 0:
        return "ACCOUNT_CONFIRMED_FLAT"
    return "ACCOUNT_NOT_FLAT"
