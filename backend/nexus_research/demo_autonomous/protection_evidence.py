"""Read-only exchange protection evidence + verdict (no writes)."""
from __future__ import annotations

from typing import Any

from backend.nexus_research.demo_exchange.readers import normalize_order_status

ACTIVE_PROTECTION_STATUSES = {"Untriggered", "New", "Active", "Triggered", "PartiallyFilled"}
TERMINAL_STATUSES = {"Filled", "Cancelled", "Rejected", "Deactivated", "Expired"}


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _norm_side(v: Any) -> str:
    return str(v or "").strip().lower()


def _is_reduce_side(position_side: str, order_side: str) -> bool:
    ps = _norm_side(position_side)
    os_ = _norm_side(order_side)
    if ps in ("buy", "long") and os_ in ("sell", "short"):
        return True
    if ps in ("sell", "short") and os_ in ("buy", "long"):
        return True
    return False


def _stop_type_role(order: dict[str, Any]) -> str | None:
    raw = " ".join(
        [
            str(order.get("stopOrderType") or ""),
            str(order.get("orderType") or ""),
        ]
    ).lower().replace("_", "").replace(" ", "")
    if not raw:
        return None
    if "takeprofit" in raw or raw in {"tp", "partialtakeprofit"}:
        return "TP"
    if "stoploss" in raw or raw in {"sl", "stop"} or "stop" in raw:
        return "SL"
    return None


def _order_active(order: dict[str, Any]) -> bool:
    status = normalize_order_status(
        order.get("normalizedOrderStatus"),
        order.get("orderStatus"),
        order.get("status"),
    )
    if status in TERMINAL_STATUSES or status == "UNKNOWN":
        return False
    return status in ACTIVE_PROTECTION_STATUSES


def _enrich_order(order: dict[str, Any]) -> dict[str, Any]:
    out = dict(order)
    out["normalizedOrderStatus"] = normalize_order_status(
        order.get("normalizedOrderStatus"),
        order.get("orderStatus"),
        order.get("status"),
    )
    if out.get("orderStatus") in (None, ""):
        out["orderStatus"] = out.get("status")
    if out.get("status") in (None, ""):
        out["status"] = out.get("orderStatus")
    return out


def _idx_compatible(pos_idx: Any, order_idx: Any) -> bool:
    """One-way (0/None) compatible; otherwise require equal idxs."""
    def _n(v: Any) -> int | None:
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    p = _n(pos_idx)
    o = _n(order_idx)
    if p in (None, 0) or o in (None, 0):
        return True
    return p == o


def _order_covers(order: dict[str, Any], pos_qty: float) -> float:
    if order.get("closeOnTrigger") is True:
        return pos_qty
    q = _f(order.get("qty"))
    return q if q is not None else 0.0


def _reduce_ok(order: dict[str, Any]) -> str:
    """Return 'ok' | 'ambiguous' | 'bad' for reduce-only / close-on-trigger evidence."""
    reduce = order.get("reduceOnly")
    close_on = order.get("closeOnTrigger")
    if reduce is True or close_on is True:
        return "ok"
    if reduce is False and close_on is not True:
        return "bad"
    return "ambiguous"


def classify_protection_orders(
    open_orders: list[dict[str, Any]],
    positions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build protectionOrders / protectionGroups / protectionVerdict (read-only)."""
    orders = [_enrich_order(o) for o in (open_orders or [])]
    active_positions = [
        p for p in (positions or []) if (_f(p.get("size")) or 0) > 0
    ]

    if not active_positions:
        return {
            "protectionVerdict": "FLAT_NOT_APPLICABLE",
            "protectionStatus": "NONE",
            "protectionActive": False,
            "openOrders": orders,
            "protectionOrders": [],
            "protectionGroups": [],
            "evidenceQuality": "N/A",
        }

    groups: list[dict[str, Any]] = []
    protection_orders: list[dict[str, Any]] = []

    for pos in active_positions:
        symbol = str(pos.get("symbol") or "")
        pos_side = str(pos.get("side") or "")
        pos_qty = float(pos.get("size") or 0)
        pos_idx = pos.get("positionIdx", pos.get("position_idx"))
        pos_tp = _f(pos.get("takeProfit"))
        pos_sl = _f(pos.get("stopLoss"))
        # Missing values stay None — do not treat absent as 0.
        trading_stop_mode = (
            pos_tp is not None and pos_sl is not None and pos_tp > 0 and pos_sl > 0
        )

        matching = [
            o
            for o in orders
            if str(o.get("symbol") or "") == symbol
            and _idx_compatible(pos_idx, o.get("positionIdx"))
        ]

        tp_order = None
        sl_order = None
        reverse_risk = False
        reduce_ambiguous = False
        active_unknown_role = []

        for o in matching:
            if not _order_active(o):
                continue
            if not _is_reduce_side(pos_side, str(o.get("side") or "")):
                reverse_risk = True
                continue
            red = _reduce_ok(o)
            if red == "bad":
                reverse_risk = True
                continue
            if red == "ambiguous":
                reduce_ambiguous = True

            role = _stop_type_role(o)
            entry = dict(o)
            entry["protectionRole"] = role or "UNKNOWN"
            protection_orders.append(entry)

            if role == "TP" and tp_order is None:
                tp_order = entry
            elif role == "SL" and sl_order is None:
                sl_order = entry
            else:
                active_unknown_role.append(entry)

        has_tp = tp_order is not None or trading_stop_mode
        has_sl = sl_order is not None or trading_stop_mode

        covered = 0.0
        if trading_stop_mode:
            covered = pos_qty
        for o in (tp_order, sl_order):
            if o:
                covered = max(covered, _order_covers(o, pos_qty))

        coverage_complete = covered + 1e-12 >= pos_qty if pos_qty > 0 else False

        trigger_verified = True
        if not trading_stop_mode:
            for o in (tp_order, sl_order):
                if o is not None and _f(o.get("triggerPrice")) is None:
                    trigger_verified = False

        reduce_verified = True
        close_verified = True
        if not trading_stop_mode:
            for o in (tp_order, sl_order):
                if o is None:
                    continue
                if _reduce_ok(o) != "ok":
                    reduce_verified = False
                if o.get("closeOnTrigger") is not True and o.get("reduceOnly") is not True:
                    close_verified = False

        if reverse_risk:
            verdict = "AMBIGUOUS"
        elif has_tp and has_sl and coverage_complete and trigger_verified:
            if trading_stop_mode:
                verdict = "PROTECTED_VERIFIED"
            elif reduce_ambiguous or not (reduce_verified or close_verified):
                verdict = "AMBIGUOUS"
            elif active_unknown_role and (tp_order is None or sl_order is None):
                verdict = "AMBIGUOUS"
            else:
                verdict = "PROTECTED_VERIFIED"
        elif has_tp or has_sl:
            verdict = "PARTIALLY_PROTECTED"
        elif active_unknown_role:
            verdict = "AMBIGUOUS"
        elif any(_order_active(o) for o in matching):
            verdict = "AMBIGUOUS"
        else:
            # No active protective orders (cancelled/filled/absent).
            verdict = "UNPROTECTED"

        if verdict == "PROTECTED_VERIFIED":
            status = "ACTIVE"
            quality = "HIGH"
        elif verdict == "PARTIALLY_PROTECTED":
            status = "PARTIAL"
            quality = "MEDIUM"
        elif verdict == "UNPROTECTED":
            status = "UNVERIFIED"
            quality = "LOW"
        else:
            status = "UNVERIFIED"
            quality = "LOW"

        groups.append(
            {
                "symbol": symbol,
                "positionIdx": 0 if pos_idx is None else pos_idx,
                "positionSide": pos_side,
                "positionQty": pos_qty,
                "coveredQty": covered if covered > 0 else None,
                "takeProfitOrder": tp_order,
                "stopLossOrder": sl_order,
                "positionTakeProfit": pos_tp,
                "positionStopLoss": pos_sl,
                "tradingStopMode": trading_stop_mode,
                "coverageComplete": coverage_complete,
                "reduceOnlyVerified": bool(trading_stop_mode or reduce_verified),
                "closeOnTriggerVerified": bool(trading_stop_mode or close_verified),
                "triggerVerified": trigger_verified,
                "status": status,
                "protectionVerdict": verdict,
                "evidenceQuality": quality,
                "reverseExposureRisk": reverse_risk,
            }
        )

    verdicts = [g["protectionVerdict"] for g in groups]
    if any(v == "AMBIGUOUS" for v in verdicts):
        overall = "AMBIGUOUS"
    elif all(v == "PROTECTED_VERIFIED" for v in verdicts):
        overall = "PROTECTED_VERIFIED"
    elif any(v == "PARTIALLY_PROTECTED" for v in verdicts):
        overall = "PARTIALLY_PROTECTED"
    elif all(v == "UNPROTECTED" for v in verdicts):
        overall = "UNPROTECTED"
    else:
        overall = "AMBIGUOUS"

    if overall == "PROTECTED_VERIFIED":
        protection_status = "ACTIVE"
    elif overall == "PARTIALLY_PROTECTED":
        protection_status = "PARTIAL"
    else:
        protection_status = "UNVERIFIED"

    return {
        "protectionVerdict": overall,
        "protectionStatus": protection_status,
        "protectionActive": overall in ("PROTECTED_VERIFIED", "PARTIALLY_PROTECTED"),
        "openOrders": orders,
        "protectionOrders": protection_orders,
        "protectionGroups": groups,
        "evidenceQuality": groups[0]["evidenceQuality"] if groups else "LOW",
    }


def protection_bool_from_orders(
    open_orders: list[dict[str, Any]], positions: list[dict[str, Any]]
) -> bool:
    return bool(classify_protection_orders(open_orders, positions).get("protectionActive"))
