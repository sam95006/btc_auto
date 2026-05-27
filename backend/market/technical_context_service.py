from __future__ import annotations

from datetime import datetime

from config.technical_context_config import (
    ATR_PERIOD,
    EMA_FAST,
    EMA_SLOW,
    KLINE_INTERVALS,
    KLINE_LIMIT,
    REGIME_EXIT_MIN_SCORE,
    RSI_PERIOD,
    TECHNICAL_CONTEXT_ENABLED,
    VOLUME_CONFIRM_RATIO,
)


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


def _parse_klines(raw):
    candles = []
    for row in list(raw or []):
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            continue
        candles.append(
            {
                "open": _safe_float(row[1]),
                "high": _safe_float(row[2]),
                "low": _safe_float(row[3]),
                "close": _safe_float(row[4]),
                "volume": _safe_float(row[5]),
            }
        )
    return candles


def _ema_series(values, period):
    if not values:
        return []
    period = max(int(period), 1)
    alpha = 2.0 / (period + 1.0)
    out = [float(values[0])]
    for value in values[1:]:
        out.append(alpha * float(value) + (1.0 - alpha) * out[-1])
    return out


def _rsi(closes, period=14):
    if len(closes) <= period:
        return 50.0
    gains = []
    losses = []
    for idx in range(1, len(closes)):
        delta = closes[idx] - closes[idx - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss <= 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(candles, period=14):
    if len(candles) <= 1:
        return 0.0
    trs = []
    for idx in range(1, len(candles)):
        prev_close = candles[idx - 1]["close"]
        high = candles[idx]["high"]
        low = candles[idx]["low"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if not trs:
        return 0.0
    window = trs[-period:]
    return sum(window) / max(len(window), 1)


def _trend_bias(close, ema_fast, ema_slow):
    if close > ema_fast > ema_slow:
        return "bullish"
    if close < ema_fast < ema_slow:
        return "bearish"
    return "neutral"


def _ema_cross(ema_fast_prev, ema_fast, ema_slow_prev, ema_slow):
    if ema_fast_prev <= ema_slow_prev and ema_fast > ema_slow:
        return "bullish_cross"
    if ema_fast_prev >= ema_slow_prev and ema_fast < ema_slow:
        return "bearish_cross"
    if ema_fast > ema_slow:
        return "bullish"
    if ema_fast < ema_slow:
        return "bearish"
    return "neutral"


def _swing_distances(candles, lookback=20):
    window = list(candles[-lookback:]) if candles else []
    if not window:
        return 0.05, 0.05
    last = window[-1]["close"]
    if last <= 0:
        return 0.05, 0.05
    high = max(item["high"] for item in window)
    low = min(item["low"] for item in window)
    support_distance = max(0.0, (last - low) / last)
    resistance_distance = max(0.0, (high - last) / last)
    return support_distance, resistance_distance


class TechnicalContextService:
    """OHLCV-based indicators for fleet/RADAR symbols (klines from Binance futures)."""

    def __init__(self, futures_client=None):
        self.futures_client = futures_client
        self._cache = {}

    def begin_tick(self):
        self._cache = {}

    def analyze(self, symbol, position_side=None):
        if not TECHNICAL_CONTEXT_ENABLED:
            return {}
        symbol = str(symbol or "").upper()
        if not symbol:
            return {}
        cache_key = (symbol, str(position_side or "").upper())
        if cache_key in self._cache:
            return self._cache[cache_key]
        if not (self.futures_client and self.futures_client.is_configured()):
            return {}

        intervals = {}
        for interval in KLINE_INTERVALS:
            try:
                raw = self.futures_client.get_klines(symbol, interval=interval, limit=KLINE_LIMIT)
                intervals[interval] = self._summarize_interval(_parse_klines(raw), interval)
            except Exception:
                intervals[interval] = {}

        flat = self._build_flat_fields(intervals, position_side=position_side)
        payload = {"intervals": intervals, "flat": flat}
        self._cache[cache_key] = payload
        return payload

    def _summarize_interval(self, candles, interval):
        if len(candles) < 5:
            return {"interval": interval, "candles": len(candles), "ready": False}

        closes = [item["close"] for item in candles]
        volumes = [item["volume"] for item in candles]
        ema_fast_series = _ema_series(closes, EMA_FAST)
        ema_slow_series = _ema_series(closes, EMA_SLOW)
        close = closes[-1]
        ema_fast = ema_fast_series[-1]
        ema_slow = ema_slow_series[-1]
        ema_fast_prev = ema_fast_series[-2] if len(ema_fast_series) > 1 else ema_fast
        ema_slow_prev = ema_slow_series[-2] if len(ema_slow_series) > 1 else ema_slow
        vol_ma = sum(volumes[-20:]) / min(len(volumes), 20)
        volume_ratio = (volumes[-1] / vol_ma) if vol_ma > 0 else 1.0
        lookback = min(10, len(closes) - 1)
        price_change = 0.0
        if lookback > 0 and closes[-lookback - 1] > 0:
            price_change = (close - closes[-lookback - 1]) / closes[-lookback - 1]
        support_distance, resistance_distance = _swing_distances(candles)

        return {
            "interval": interval,
            "candles": len(candles),
            "ready": True,
            "close": round(close, 8),
            "open": round(candles[-1]["open"], 8),
            "high": round(candles[-1]["high"], 8),
            "low": round(candles[-1]["low"], 8),
            "volume": round(volumes[-1], 4),
            "volume_ma": round(vol_ma, 4),
            "volume_ratio": round(volume_ratio, 4),
            "rsi_14": round(_rsi(closes, RSI_PERIOD), 4),
            "ema_20": round(ema_fast, 8),
            "ema_50": round(ema_slow, 8),
            "atr_14": round(_atr(candles, ATR_PERIOD), 8),
            "price_change": round(price_change, 6),
            "support_distance": round(support_distance, 6),
            "resistance_distance": round(resistance_distance, 6),
            "trend_bias": _trend_bias(close, ema_fast, ema_slow),
            "ema_cross": _ema_cross(ema_fast_prev, ema_fast, ema_slow_prev, ema_slow),
        }

    def _build_flat_fields(self, intervals, position_side=None):
        primary = intervals.get("15m") or intervals.get("5m") or next(iter(intervals.values()), {})
        fast = intervals.get("5m") or primary
        if not primary.get("ready"):
            return {}

        close = _safe_float(primary.get("close"))
        atr = _safe_float(primary.get("atr_14"))
        atr_pct = (atr / close) if close > 0 else 0.0
        support_distance = _safe_float(primary.get("support_distance"), 0.05)
        resistance_distance = _safe_float(primary.get("resistance_distance"), 0.05)

        trend_strength = _safe_float(primary.get("price_change"))
        volume_confirmed = _safe_float(fast.get("volume_ratio")) >= VOLUME_CONFIRM_RATIO
        trend_bias = str(primary.get("trend_bias") or "neutral")
        fast_bias = str(fast.get("trend_bias") or trend_bias)
        regime_change = trend_bias != fast_bias and trend_bias != "neutral" and fast_bias != "neutral"
        technical_exit_score = self._technical_exit_score(position_side, primary, fast)

        return {
            "trend_strength": round(trend_strength, 6),
            "volatility_percentile": round(min(1.0, atr_pct / 0.03), 6),
            "volume_confirmed": volume_confirmed,
            "support_distance": round(support_distance, 6),
            "resistance_distance": round(resistance_distance, 6),
            "rsi_14": primary.get("rsi_14"),
            "ema_20": primary.get("ema_20"),
            "ema_50": primary.get("ema_50"),
            "atr_14": primary.get("atr_14"),
            "atr_pct": round(atr_pct, 6),
            "volume_ratio": fast.get("volume_ratio"),
            "price_change_5m": fast.get("price_change"),
            "price_change_15m": primary.get("price_change"),
            "trend_bias": trend_bias,
            "ema_cross": primary.get("ema_cross"),
            "regime_change": regime_change,
            "technical_exit_score": round(technical_exit_score, 4),
            "technical_ready": True,
            "technical_updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _technical_exit_score(self, position_side, primary, fast):
        side = str(position_side or "").upper()
        score = 0.0
        trend = str(primary.get("trend_bias") or "neutral")
        ema_cross = str(primary.get("ema_cross") or "neutral")
        rsi = _safe_float(primary.get("rsi_14"), 50.0)
        fast_change = _safe_float(fast.get("price_change"))
        volume_ratio = _safe_float(fast.get("volume_ratio"), 1.0)

        if side == "LONG":
            if trend == "bearish":
                score += 0.35
            if ema_cross in {"bearish", "bearish_cross"}:
                score += 0.25
            if rsi < 45:
                score += 0.2
            if volume_ratio >= 1.25 and fast_change < 0:
                score += 0.2
        elif side == "SHORT":
            if trend == "bullish":
                score += 0.35
            if ema_cross in {"bullish", "bullish_cross"}:
                score += 0.25
            if rsi > 55:
                score += 0.2
            if volume_ratio >= 1.25 and fast_change > 0:
                score += 0.2
        else:
            if trend != "neutral":
                score += 0.2
            if ema_cross.endswith("_cross"):
                score += 0.25

        if score < REGIME_EXIT_MIN_SCORE and str(primary.get("trend_bias")) != str(fast.get("trend_bias")):
            score = max(score, 0.45)
        return min(1.0, score)
