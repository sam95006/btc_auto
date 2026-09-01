"""Backend-computed, member-safe live market showcase for the Corporate site.

Reuses the existing credential-free public market snapshot service. Market
regime and risk are computed HERE (backend), so the frontend only renders/
animates the backend's decision — it never fabricates a value. No private
execution, Founder positions, or private PnL are exposed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _unavailable(reason: str, symbols: tuple[str, ...]) -> dict[str, Any]:
    return {
        "availability": "UNAVAILABLE",
        "reason": reason,
        "source": "binance_usdm_public",
        "updated_at": _utc_now(),
        "freshness": "UNAVAILABLE",
        "symbols": [{"symbol": s, "availability": "UNAVAILABLE"} for s in symbols],
        "regime": {"value": None, "availability": "UNAVAILABLE"},
        "risk": {"value": None, "availability": "UNAVAILABLE"},
    }


def build_showcase(snapshot_service: Any, symbols: tuple[str, ...] = DEFAULT_SYMBOLS) -> dict[str, Any]:
    """Return the redacted showcase payload. Never invents fallback numbers."""
    if snapshot_service is None:
        return _unavailable("market_source_unbound", symbols)
    try:
        payload, status = snapshot_service.snapshot()
    except Exception:  # noqa: BLE001
        return _unavailable("market_source_error", symbols)
    if status != 200 or not payload.get("symbols"):
        return _unavailable("market_data_unavailable", symbols)

    by = {row.get("symbol"): row for row in payload.get("symbols", [])}
    fallback = payload.get("fallback")
    feed_fresh = "STALE" if fallback == "last_known_value" else "FRESH"

    out_symbols: list[dict[str, Any]] = []
    changes: list[float] = []
    ranges: list[float] = []
    for sym in symbols:
        row = by.get(sym)
        price = (row or {}).get("current_price")
        if not row or price is None:
            out_symbols.append({"symbol": sym, "availability": "UNAVAILABLE"})
            continue
        high, low = row.get("high_24h"), row.get("low_24h")
        range_pct = round(((high - low) / low * 100.0), 4) if isinstance(high, (int, float)) and isinstance(low, (int, float)) and low else None
        change = row.get("change_24h_percent")
        volatility = None
        if isinstance(range_pct, (int, float)):
            volatility = "high" if range_pct >= 8 else "moderate" if range_pct >= 3 else "low"
        if isinstance(change, (int, float)):
            changes.append(float(change))
        if isinstance(range_pct, (int, float)):
            ranges.append(float(range_pct))
        out_symbols.append({
            "symbol": sym,
            "price": price,
            "change_24h_percent": change,
            "high_24h": high if isinstance(high, (int, float)) else None,
            "low_24h": low if isinstance(low, (int, float)) else None,
            "volume_24h": row.get("volume_24h"),
            "range_pct": range_pct,
            "volatility": volatility,
            "availability": "READY",
            "freshness": row.get("freshness") or feed_fresh,
            "source": "binance_usdm_public",
            "provider_timestamp": row.get("provider_timestamp"),
        })

    # Backend-decided regime + risk (deterministic, member-safe, public-derived).
    regime_val = None
    if changes:
        avg = sum(changes) / len(changes)
        regime_val = "RISK_ON" if avg > 1.0 else "RISK_OFF" if avg < -1.0 else "NEUTRAL"
    risk_val = None
    if ranges:
        avg_r = sum(ranges) / len(ranges)
        risk_val = "elevated" if avg_r >= 8 else "moderate" if avg_r >= 3 else "contained"

    return {
        "availability": "READY",
        "source": "binance_usdm_public",
        "updated_at": payload.get("server_timestamp") or _utc_now(),
        "freshness": feed_fresh,
        "data_class": "MEMBER_SAFE_PUBLIC_MARKET",
        "symbols": out_symbols,
        "regime": {"value": regime_val, "basis": "avg_24h_change", "availability": "READY" if regime_val else "UNAVAILABLE"},
        "risk": {"value": risk_val, "basis": "avg_24h_range", "availability": "READY" if risk_val else "UNAVAILABLE"},
    }
