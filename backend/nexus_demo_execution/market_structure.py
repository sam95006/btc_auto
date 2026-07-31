"""Market structure inputs from public klines — no future data, no invented levels."""
from __future__ import annotations

from typing import Any


def _f(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def atr_from_ohlc(candles: list[dict[str, float]], period: int = 14) -> float | None:
    """Classic ATR; requires period+1 bars. Returns None if insufficient."""
    if len(candles) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        prev_c = candles[i - 1]["close"]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    if len(trs) < period:
        return None
    window = trs[-period:]
    return sum(window) / float(period)


def swing_high_low(candles: list[dict[str, float]], lookback: int = 20) -> tuple[float | None, float | None]:
    if not candles:
        return None, None
    window = candles[-lookback:] if len(candles) >= lookback else candles
    highs = [c["high"] for c in window if c["high"] > 0]
    lows = [c["low"] for c in window if c["low"] > 0]
    if not highs or not lows:
        return None, None
    return max(highs), min(lows)


def support_resistance_from_swings(
    *,
    last: float,
    swing_high: float | None,
    swing_low: float | None,
) -> tuple[float | None, float | None]:
    """Minimal structure: nearest swing below = support, nearest swing above = resistance."""
    support = swing_low if swing_low is not None and swing_low < last else None
    resistance = swing_high if swing_high is not None and swing_high > last else None
    return support, resistance


def parse_bybit_kline_list(raw: list[Any]) -> list[dict[str, float]]:
    """Bybit kline list is newest-first; reverse to chronological."""
    out: list[dict[str, float]] = []
    for item in raw:
        if isinstance(item, list) and len(item) >= 5:
            out.append(
                {
                    "open": _f(item[1]),
                    "high": _f(item[2]),
                    "low": _f(item[3]),
                    "close": _f(item[4]),
                    "volume": _f(item[5]) if len(item) > 5 else 0.0,
                }
            )
    out.reverse()
    return out


def build_geometry_inputs_from_klines(
    *,
    last_price: float,
    klines: list[dict[str, float]],
    atr_period: int = 14,
    swing_lookback: int = 20,
    tick_size: float | None = None,
    qty_step: float | None = None,
) -> dict[str, Any]:
    atr = atr_from_ohlc(klines, period=atr_period)
    sh, sl = swing_high_low(klines, lookback=swing_lookback)
    support, resistance = support_resistance_from_swings(last=last_price, swing_high=sh, swing_low=sl)
    missing: list[str] = []
    if atr is None:
        missing.append("atr")
    if sh is None:
        missing.append("recent_swing_high")
    if sl is None:
        missing.append("recent_swing_low")
    if support is None:
        missing.append("support")
    if resistance is None:
        missing.append("resistance")
    return {
        "atr": atr if atr is not None else "UNAVAILABLE",
        "atr_period": atr_period,
        "recent_swing_high": sh if sh is not None else "UNAVAILABLE",
        "recent_swing_low": sl if sl is not None else "UNAVAILABLE",
        "support": support if support is not None else "UNAVAILABLE",
        "resistance": resistance if resistance is not None else "UNAVAILABLE",
        "support_levels": [support] if support is not None else [],
        "resistance_levels": [resistance] if resistance is not None else [],
        "liquidity_above": [resistance] if resistance is not None else [],
        "liquidity_below": [support] if support is not None else [],
        "tick_size": tick_size if tick_size is not None else "UNAVAILABLE",
        "qty_step": qty_step if qty_step is not None else "UNAVAILABLE",
        "geometry_status": "GEOMETRY_INPUT_MISSING" if missing else "GEOMETRY_INPUTS_COMPLETE",
        "geometry_missing_fields": missing,
        "bars_used": len(klines),
    }
