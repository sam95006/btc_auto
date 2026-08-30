"""Deterministic, member-safe analysis + report generation (PERSONAL-1).

No external AI is required or used. Analysis is a deterministic read-only
computation over a market price series supplied by an injectable market source
(the real public market service in production; a fixture in tests). The output
is member-safe: it contains NO trading execution fields, order routing, position
sizing, ARM, or private decision objects.

If no market data is available the caller returns an explicit unavailable state
(and does not consume quota) rather than fabricating data.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence


class AnalysisDataUnavailable(Exception):
    """Raised when there is no market series to analyze (fail safe, no fake data)."""


def analyze_series(symbol: str, series: Optional[Sequence[float]]) -> dict[str, Any]:
    values = [float(v) for v in (series or []) if isinstance(v, (int, float))]
    if len(values) < 2:
        raise AnalysisDataUnavailable("insufficient_market_data")

    first, last = values[0], values[-1]
    high, low = max(values), min(values)
    change_pct = ((last - first) / first * 100.0) if first else 0.0
    span_pct = ((high - low) / low * 100.0) if low else 0.0

    if change_pct > 1.0:
        trend = "up"
    elif change_pct < -1.0:
        trend = "down"
    else:
        trend = "flat"

    if span_pct >= 8.0:
        volatility = "high"
    elif span_pct >= 3.0:
        volatility = "moderate"
    else:
        volatility = "low"

    # Member-safe result only. Deliberately no execution/sizing/routing fields.
    return {
        "data_class": "MEMBER_SAFE_ANALYSIS",
        "symbol": symbol,
        "points": len(values),
        "trend": trend,
        "volatility": volatility,
        "change_pct": round(change_pct, 4),
        "range_pct": round(span_pct, 4),
    }


def build_report(
    symbol: str,
    analysis: dict[str, Any],
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """A deterministic member-safe report derived from a completed analysis.

    `metadata` carries member-safe provenance only (symbol, interval, provider,
    source_class, freshness, data/analysis timestamps, points). It must never
    include exchange keys, order IDs, routing, ARM, or position sizing.
    """
    meta = dict(metadata or {})
    return {
        "data_class": "MEMBER_SAFE_REPORT",
        "symbol": symbol,
        "summary": f"{symbol}: trend={analysis.get('trend')} volatility={analysis.get('volatility')}",
        "sections": [
            {"title": "趨勢", "value": analysis.get("trend")},
            {"title": "波動度", "value": analysis.get("volatility")},
            {"title": "區間變化 %", "value": analysis.get("range_pct")},
        ],
        "provenance": {
            "provider": meta.get("provider"),
            "source_class": meta.get("source_class"),
            "freshness": meta.get("freshness"),
            "data_timestamp": meta.get("data_timestamp"),
            "analysis_timestamp": meta.get("analysis_timestamp"),
            "interval": meta.get("interval"),
        },
    }


def assess_risk(analysis: dict[str, Any]) -> dict[str, Any]:
    """Deterministic member-safe *market* risk descriptor from real volatility.

    This is read-only market-risk information (a volatility band), explicitly
    NOT Risk Guard, position sizing, leverage authority, routing, ARM, or any
    private trade state. It only reflects the observed public price range.
    """
    range_pct = float(analysis.get("range_pct") or 0.0)
    volatility = str(analysis.get("volatility") or "low")
    if range_pct >= 8.0:
        level = "elevated"
    elif range_pct >= 3.0:
        level = "moderate"
    else:
        level = "contained"
    return {
        "data_class": "MEMBER_SAFE_RISK",
        "symbol": analysis.get("symbol"),
        "risk_level": level,
        "volatility": volatility,
        "range_pct": round(range_pct, 4),
        "basis": "observed_public_price_range",
    }
