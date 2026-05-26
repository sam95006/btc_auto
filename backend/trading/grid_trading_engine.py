from __future__ import annotations

from statistics import mean


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


class GridTradingEngine:
    """Range-grid signal generator: buy dips / sell rips inside a rolling band."""

    def __init__(self, lookback_ticks=24, spacing_pct=0.0035, range_max_deviation_pct=0.018):
        self.lookback_ticks = max(8, int(lookback_ticks or 24))
        self.spacing_pct = max(0.001, float(spacing_pct or 0.0035))
        self.range_max_deviation_pct = max(0.005, float(range_max_deviation_pct or 0.018))

    def evaluate(self, symbol, price, history, market_context=None):
        market_context = market_context or {}
        price = _safe_float(price)
        if price <= 0:
            return None

        series = [ _safe_float(item) for item in list(history or []) if _safe_float(item) > 0 ]
        if len(series) < self.lookback_ticks:
            return None

        window = series[-self.lookback_ticks :]
        mid = mean(window)
        if mid <= 0:
            return None

        deviation = abs(price - mid) / mid
        vol_pct = _safe_float(market_context.get("volatility_percentile"), 0.5)
        regime = str(market_context.get("market_regime") or "normal").lower()
        if deviation > self.range_max_deviation_pct:
            return None
        if vol_pct > _safe_float(market_context.get("grid_max_vol"), 0.72):
            return None
        if regime in {"crash", "liquidation_risk", "extreme_volatility", "news_shock"}:
            return None

        spacing = max(mid * self.spacing_pct, price * 0.0008)
        lower = mid - spacing
        upper = mid + spacing
        prev = _safe_float(series[-2], price)

        side = None
        confidence = 0.5
        if price <= lower and prev > lower:
            side = "BUY"
            confidence = min(0.72, 0.48 + (lower - price) / max(spacing, 1e-9) * 0.12)
        elif price >= upper and prev < upper:
            side = "SELL"
            confidence = min(0.72, 0.48 + (price - upper) / max(spacing, 1e-9) * 0.12)

        if not side:
            return None

        return {
            "symbol": str(symbol or "").upper(),
            "side": side,
            "confidence": round(confidence, 4),
            "mid": round(mid, 8),
            "spacing": round(spacing, 8),
            "deviation_pct": round(deviation * 100, 4),
            "volatility_percentile": round(vol_pct, 4),
            "setup": "range_grid",
        }
