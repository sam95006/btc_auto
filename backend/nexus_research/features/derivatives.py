"""NEXUS Phase 6.4 — Derivatives Market Data Normalization.

Normalizes:
- Funding rate
- Open interest (OI)
- Long/short ratio
- Liquidations
- Mark price / index price / basis

Policy:
- NEVER fill missing values with 0 — use UNAVAILABLE
- All fields carry freshness / quality indicators

Quality levels:
  LIVE        — data received and fresh
  STALE       — data older than threshold
  UNAVAILABLE — missing or null
"""
from __future__ import annotations

import datetime
import time
from typing import Any, Optional


def _utc_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _unavail(reason: str, field_name: str = "") -> dict[str, Any]:
    return {
        "value": None,
        "quality": "UNAVAILABLE",
        "reason": reason,
        "field": field_name,
    }


def _freshness_label(data_ts_ms: Optional[int], now_ms: Optional[int] = None, stale_threshold_ms: int = 120_000) -> str:
    """Return LIVE / STALE / UNAVAILABLE based on data timestamp vs now."""
    if data_ts_ms is None:
        return "UNAVAILABLE"
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    age = now - data_ts_ms
    return "LIVE" if age <= stale_threshold_ms else "STALE"


def _safe_float(val: Any, field: str) -> dict[str, Any]:
    """Try to parse val as float; return UNAVAILABLE on failure or None."""
    if val is None:
        return _unavail("missing_value", field)
    try:
        f = float(val)
        return {"value": f, "quality": "COMPLETE"}
    except (TypeError, ValueError):
        return _unavail(f"parse_error:{val!r}", field)


# ─────────────────────────────────────────────────────────────────────────────
# Funding Rate
# ─────────────────────────────────────────────────────────────────────────────

def normalize_funding(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw funding rate payload.

    Expected keys (all optional — missing → UNAVAILABLE):
      fundingRate, nextFundingTime, fundingRateTimestamp, symbol
    """
    symbol = str(raw.get("symbol") or "")
    funding_raw = raw.get("fundingRate")
    next_time = raw.get("nextFundingTime")
    ts_ms = raw.get("fundingRateTimestamp") or raw.get("ts")
    rate = _safe_float(funding_raw, "fundingRate")
    rate_pct = {"value": rate["value"] * 100.0, "quality": rate["quality"]} if rate["value"] is not None else _unavail("funding_rate_unavailable", "fundingRatePct")
    freshness = _freshness_label(int(ts_ms) if ts_ms is not None else None)
    annualized = None
    if rate["value"] is not None:
        annualized = rate["value"] * 3 * 365  # 3x daily (8h funding)
    return {
        "symbol": symbol,
        "fundingRate": rate,
        "fundingRatePct": rate_pct,
        "annualizedFundingRate": {"value": annualized, "quality": "COMPLETE"} if annualized is not None else _unavail("funding_rate_unavailable", "annualizedFundingRate"),
        "nextFundingTime": next_time,
        "dataTimestampMs": ts_ms,
        "freshness": freshness,
        "researchOnly": True,
        "privateApi": False,
        "generatedAt": _utc_iso(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Open Interest
# ─────────────────────────────────────────────────────────────────────────────

def normalize_open_interest(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize open interest payload.

    Expected keys: openInterest, openInterestValue, symbol, ts
    """
    symbol = str(raw.get("symbol") or "")
    ts_ms = raw.get("ts") or raw.get("timestamp")
    oi = _safe_float(raw.get("openInterest"), "openInterest")
    oi_value = _safe_float(raw.get("openInterestValue"), "openInterestValue")
    freshness = _freshness_label(int(ts_ms) if ts_ms is not None else None)
    return {
        "symbol": symbol,
        "openInterest": oi,
        "openInterestValue": oi_value,
        "dataTimestampMs": ts_ms,
        "freshness": freshness,
        "researchOnly": True,
        "privateApi": False,
        "generatedAt": _utc_iso(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Long / Short Ratio
# ─────────────────────────────────────────────────────────────────────────────

def normalize_long_short_ratio(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize long/short ratio payload.

    Expected keys: longShortRatio, longAccount, shortAccount, symbol, timestamp
    """
    symbol = str(raw.get("symbol") or "")
    ts_ms = raw.get("timestamp") or raw.get("ts")
    ratio = _safe_float(raw.get("longShortRatio"), "longShortRatio")
    long_acc = _safe_float(raw.get("longAccount"), "longAccount")
    short_acc = _safe_float(raw.get("shortAccount"), "shortAccount")
    freshness = _freshness_label(int(ts_ms) if ts_ms is not None else None)
    # Cross-validate: longAccount + shortAccount should ≈ 1
    cross_valid = None
    if long_acc["value"] is not None and short_acc["value"] is not None:
        total = long_acc["value"] + short_acc["value"]
        cross_valid = abs(total - 1.0) < 0.01
    return {
        "symbol": symbol,
        "longShortRatio": ratio,
        "longAccount": long_acc,
        "shortAccount": short_acc,
        "crossValidation": {"sumNearOne": cross_valid},
        "dataTimestampMs": ts_ms,
        "freshness": freshness,
        "researchOnly": True,
        "privateApi": False,
        "generatedAt": _utc_iso(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Liquidations
# ─────────────────────────────────────────────────────────────────────────────

def normalize_liquidations(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a liquidation event or aggregate payload.

    Expected keys for aggregate: longLiquidations, shortLiquidations,
                                  longLiquidationsValue, shortLiquidationsValue,
                                  symbol, ts
    Expected keys for single event: side, qty, price, symbol, ts
    """
    symbol = str(raw.get("symbol") or "")
    ts_ms = raw.get("ts") or raw.get("timestamp")
    freshness = _freshness_label(int(ts_ms) if ts_ms is not None else None)
    # Aggregate form
    if "longLiquidations" in raw or "shortLiquidations" in raw:
        long_liq = _safe_float(raw.get("longLiquidations"), "longLiquidations")
        short_liq = _safe_float(raw.get("shortLiquidations"), "shortLiquidations")
        long_val = _safe_float(raw.get("longLiquidationsValue"), "longLiquidationsValue")
        short_val = _safe_float(raw.get("shortLiquidationsValue"), "shortLiquidationsValue")
        net = None
        if long_val["value"] is not None and short_val["value"] is not None:
            net = long_val["value"] - short_val["value"]
        return {
            "symbol": symbol,
            "form": "aggregate",
            "longLiquidations": long_liq,
            "shortLiquidations": short_liq,
            "longLiquidationsValue": long_val,
            "shortLiquidationsValue": short_val,
            "netLiquidationValue": {"value": net, "quality": "COMPLETE"} if net is not None else _unavail("components_missing", "netLiquidationValue"),
            "dataTimestampMs": ts_ms,
            "freshness": freshness,
            "researchOnly": True,
            "privateApi": False,
            "generatedAt": _utc_iso(),
        }
    # Single event form
    side = str(raw.get("side") or "")
    qty = _safe_float(raw.get("qty") or raw.get("size"), "qty")
    price = _safe_float(raw.get("price"), "price")
    notional = None
    if qty["value"] is not None and price["value"] is not None:
        notional = qty["value"] * price["value"]
    return {
        "symbol": symbol,
        "form": "event",
        "side": side if side else None,
        "qty": qty,
        "price": price,
        "notionalValue": {"value": notional, "quality": "COMPLETE"} if notional is not None else _unavail("qty_or_price_missing", "notionalValue"),
        "dataTimestampMs": ts_ms,
        "freshness": freshness,
        "researchOnly": True,
        "privateApi": False,
        "generatedAt": _utc_iso(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Mark / Index / Basis
# ─────────────────────────────────────────────────────────────────────────────

def normalize_mark_index_basis(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize mark price, index price, basis.

    Expected keys: markPrice, indexPrice, lastPrice, symbol, ts
    Basis = markPrice - indexPrice (NEVER fabricated if either is missing)
    """
    symbol = str(raw.get("symbol") or "")
    ts_ms = raw.get("ts") or raw.get("timestamp")
    freshness = _freshness_label(int(ts_ms) if ts_ms is not None else None)
    mark = _safe_float(raw.get("markPrice"), "markPrice")
    index = _safe_float(raw.get("indexPrice"), "indexPrice")
    last = _safe_float(raw.get("lastPrice"), "lastPrice")
    basis = _unavail("mark_or_index_missing", "basis")
    basis_pct = _unavail("mark_or_index_missing", "basisPct")
    if mark["value"] is not None and index["value"] is not None:
        b = mark["value"] - index["value"]
        b_pct = b / index["value"] * 100.0 if index["value"] != 0 else None
        basis = {"value": b, "quality": "COMPLETE"}
        basis_pct = {"value": b_pct, "quality": "COMPLETE"} if b_pct is not None else _unavail("zero_index", "basisPct")
    return {
        "symbol": symbol,
        "markPrice": mark,
        "indexPrice": index,
        "lastPrice": last,
        "basis": basis,
        "basisPct": basis_pct,
        "dataTimestampMs": ts_ms,
        "freshness": freshness,
        "researchOnly": True,
        "privateApi": False,
        "generatedAt": _utc_iso(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Composite normalizer
# ─────────────────────────────────────────────────────────────────────────────

def normalize_derivatives_snapshot(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a combined derivatives snapshot (ticker-style payload)."""
    symbol = str(raw.get("symbol") or "")
    return {
        "symbol": symbol,
        "funding": normalize_funding(raw),
        "openInterest": normalize_open_interest(raw),
        "markIndexBasis": normalize_mark_index_basis(raw),
        "researchOnly": True,
        "generatedAt": _utc_iso(),
    }
