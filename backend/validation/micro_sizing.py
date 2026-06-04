"""Phase 3.1 — micro validation final sizing clamp (isolated from global MIN_MARGIN)."""

from __future__ import annotations

from typing import Any, Optional, Tuple

from config.fee_churn_config import MIN_NOTIONAL_USD
from config.micro_validation_config import (
    MICRO_VALIDATION_MAX_LEVERAGE,
    MICRO_VALIDATION_MAX_MARGIN_USD,
    is_micro_sizing_request,
)

FALLBACK_GLOBAL_MIN_NOTIONAL_REASON = "exchange_filter_unavailable_fallback_global_min_notional"


def parse_min_notional_from_symbol_info(symbol_info: Any) -> Optional[float]:
    """Parse Binance futures MIN_NOTIONAL / NOTIONAL filter from exchangeInfo symbol payload."""
    for flt in (symbol_info or {}).get("filters") or []:
        filter_type = str(flt.get("filterType") or "")
        if filter_type not in {"MIN_NOTIONAL", "NOTIONAL"}:
            continue
        raw = flt.get("notional")
        if raw is None:
            raw = flt.get("minNotional")
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def resolve_micro_exchange_min_notional(futures_client, symbol: str) -> Tuple[Optional[float], Optional[str]]:
    sym = str(symbol or "").upper().replace("/", "")
    if not sym or futures_client is None:
        return None, FALLBACK_GLOBAL_MIN_NOTIONAL_REASON
    try:
        is_configured = getattr(futures_client, "is_configured", None)
        if callable(is_configured) and not is_configured():
            return None, FALLBACK_GLOBAL_MIN_NOTIONAL_REASON
        get_symbol_info = getattr(futures_client, "get_symbol_info", None)
        if not callable(get_symbol_info):
            return None, FALLBACK_GLOBAL_MIN_NOTIONAL_REASON
        min_notional = parse_min_notional_from_symbol_info(get_symbol_info(sym))
        if min_notional is not None and min_notional > 0:
            return float(min_notional), None
    except Exception:
        pass
    return None, FALLBACK_GLOBAL_MIN_NOTIONAL_REASON


def resolve_effective_min_notional(
    exchange_min_notional: Optional[float] = None,
) -> Tuple[float, Optional[str]]:
    if exchange_min_notional is not None and float(exchange_min_notional) > 0:
        return float(exchange_min_notional), None
    return float(MIN_NOTIONAL_USD), FALLBACK_GLOBAL_MIN_NOTIONAL_REASON


def apply_final_micro_sizing_clamp(
    request,
    *,
    min_notional_usd: Optional[float] = None,
) -> Tuple[dict, Optional[str]]:
    request = dict(request or {})
    if not is_micro_sizing_request(request):
        return request, None

    max_margin = float(MICRO_VALIDATION_MAX_MARGIN_USD)
    max_leverage = int(MICRO_VALIDATION_MAX_LEVERAGE)
    leverage = min(max(int(request.get("leverage") or max_leverage), 1), max_leverage)
    margin = min(float(request.get("margin") or max_margin), max_margin)

    min_notional, fallback_reason = resolve_effective_min_notional(min_notional_usd)
    if fallback_reason:
        request["micro_sizing_min_notional_fallback_reason"] = fallback_reason
    else:
        request.pop("micro_sizing_min_notional_fallback_reason", None)
    request["micro_sizing_min_notional_used"] = round(min_notional, 4)

    min_margin_needed = min_notional / float(leverage)
    if min_margin_needed > max_margin + 1e-6:
        return request, "exchange_min_notional_exceeds_micro_cap"

    notional = margin * leverage
    if notional + 1e-6 < min_notional:
        return request, "exchange_min_notional_exceeds_micro_cap"

    request["margin"] = round(margin, 4)
    request["leverage"] = leverage
    request["micro_sizing_override"] = True
    request["micro_sizing_final_margin"] = request["margin"]
    request["micro_sizing_final_leverage"] = leverage
    return request, None
