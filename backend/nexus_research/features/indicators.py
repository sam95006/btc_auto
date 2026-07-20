"""NEXUS Phase 6.4 — Pure Technical Indicator Functions.

All functions are:
- Pure (no side effects, no global state)
- Deterministic (same input → same output)
- No future leakage (value at index i uses only bars[0..i])
- No external dependencies (pure Python math only)

Input candle format: list of dicts with keys:
  open, high, low, close, volume, ts (required)
  turnover (optional)
  incomplete (optional bool — marks last candle as partially formed)

Quality fields:
  COMPLETE   — full bar data available
  INCOMPLETE — last candle flagged as not yet closed
  UNAVAILABLE — insufficient data for calculation
"""
from __future__ import annotations

import math
from typing import Any

FORMULA_VERSION: dict[str, str] = {
    "SMA": "1.0",
    "EMA": "1.0",
    "VWAP": "1.0",
    "RSI": "1.0",
    "MACD": "1.0",
    "ATR": "1.0",
    "ADX": "1.0",
    "BOLLINGER": "1.0",
    "SUPERTREND": "1.0",
    "RETURNS": "1.0",
    "REALIZED_VOL": "1.0",
    "VOLUME_ZSCORE": "1.0",
    "PRICE_DIST_VWAP": "1.0",
    "TREND_SLOPE": "1.0",
}

_Q_COMPLETE = "COMPLETE"
_Q_INCOMPLETE = "INCOMPLETE"
_Q_UNAVAILABLE = "UNAVAILABLE"


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _closes(bars: list[dict[str, Any]]) -> list[float]:
    return [float(b["close"]) for b in bars]


def _highs(bars: list[dict[str, Any]]) -> list[float]:
    return [float(b["high"]) for b in bars]


def _lows(bars: list[dict[str, Any]]) -> list[float]:
    return [float(b["low"]) for b in bars]


def _volumes(bars: list[dict[str, Any]]) -> list[float]:
    return [float(b["volume"]) for b in bars]


def _last_quality(bars: list[dict[str, Any]]) -> str:
    """Return INCOMPLETE if the last bar is flagged, else COMPLETE."""
    if bars and bars[-1].get("incomplete"):
        return _Q_INCOMPLETE
    return _Q_COMPLETE


def _unavail(reason: str) -> dict[str, Any]:
    return {"value": None, "quality": _Q_UNAVAILABLE, "reason": reason}


# ─────────────────────────────────────────────────────────────────────────────
# SMA — Simple Moving Average
# ─────────────────────────────────────────────────────────────────────────────

def sma(bars: list[dict[str, Any]], period: int = 20) -> dict[str, Any]:
    """SMA of close prices. Returns value at last bar using only past data."""
    if not bars:
        return _unavail("no_bars")
    closes = _closes(bars)
    n = len(closes)
    if n < period:
        return _unavail(f"insufficient_bars:{n}<{period}")
    window = closes[n - period:]
    value = sum(window) / period
    return {"value": value, "quality": _last_quality(bars), "period": period,
            "formula_version": FORMULA_VERSION["SMA"]}


def sma_series(bars: list[dict[str, Any]], period: int = 20) -> list[float | None]:
    """Full SMA series, None where insufficient data. No lookahead."""
    closes = _closes(bars)
    result: list[float | None] = []
    for i in range(len(closes)):
        if i < period - 1:
            result.append(None)
        else:
            result.append(sum(closes[i - period + 1: i + 1]) / period)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# EMA — Exponential Moving Average
# ─────────────────────────────────────────────────────────────────────────────

def ema_series(bars: list[dict[str, Any]], period: int = 20) -> list[float | None]:
    """Full EMA series. Seeded with SMA of first `period` bars."""
    closes = _closes(bars)
    result: list[float | None] = [None] * len(closes)
    if len(closes) < period:
        return result
    k = 2.0 / (period + 1)
    seed = sum(closes[:period]) / period
    result[period - 1] = seed
    for i in range(period, len(closes)):
        result[i] = closes[i] * k + result[i - 1] * (1 - k)  # type: ignore[operator]
    return result


def ema(bars: list[dict[str, Any]], period: int = 20) -> dict[str, Any]:
    """EMA of close prices at last bar."""
    if not bars:
        return _unavail("no_bars")
    series = ema_series(bars, period)
    val = series[-1]
    if val is None:
        return _unavail(f"insufficient_bars:{len(bars)}<{period}")
    return {"value": val, "quality": _last_quality(bars), "period": period,
            "formula_version": FORMULA_VERSION["EMA"]}


# ─────────────────────────────────────────────────────────────────────────────
# VWAP — Volume-Weighted Average Price (session/cumulative)
# ─────────────────────────────────────────────────────────────────────────────

def vwap(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Cumulative VWAP over provided bars (no session reset)."""
    if not bars:
        return _unavail("no_bars")
    cum_tp_vol = 0.0
    cum_vol = 0.0
    for b in bars:
        tp = (float(b["high"]) + float(b["low"]) + float(b["close"])) / 3.0
        v = float(b["volume"])
        cum_tp_vol += tp * v
        cum_vol += v
    if cum_vol == 0.0:
        return _unavail("zero_volume")
    value = cum_tp_vol / cum_vol
    return {"value": value, "quality": _last_quality(bars), "cumulativeVolume": cum_vol,
            "formula_version": FORMULA_VERSION["VWAP"]}


# ─────────────────────────────────────────────────────────────────────────────
# RSI — Relative Strength Index (Wilder smoothing)
# ─────────────────────────────────────────────────────────────────────────────

def rsi(bars: list[dict[str, Any]], period: int = 14) -> dict[str, Any]:
    """RSI using Wilder's exponential smoothing. No lookahead."""
    if not bars:
        return _unavail("no_bars")
    closes = _closes(bars)
    if len(closes) < period + 1:
        return _unavail(f"insufficient_bars:{len(closes)}<{period + 1}")
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    # Seed with simple average over first `period` diffs
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0.0:
        value = 100.0
    else:
        rs = avg_gain / avg_loss
        value = 100.0 - 100.0 / (1.0 + rs)
    return {"value": value, "quality": _last_quality(bars), "period": period,
            "formula_version": FORMULA_VERSION["RSI"]}


# ─────────────────────────────────────────────────────────────────────────────
# MACD
# ─────────────────────────────────────────────────────────────────────────────

def macd(
    bars: list[dict[str, Any]],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, Any]:
    """MACD line, signal line, histogram."""
    if not bars:
        return _unavail("no_bars")
    if len(bars) < slow + signal:
        return _unavail(f"insufficient_bars:{len(bars)}<{slow + signal}")
    fast_ema = ema_series(bars, fast)
    slow_ema = ema_series(bars, slow)
    macd_line: list[float | None] = []
    for f, s in zip(fast_ema, slow_ema):
        if f is None or s is None:
            macd_line.append(None)
        else:
            macd_line.append(f - s)
    # Signal: EMA of macd_line (only non-None values)
    valid_indices = [i for i, v in enumerate(macd_line) if v is not None]
    if len(valid_indices) < signal:
        return _unavail(f"insufficient_macd_values:{len(valid_indices)}<{signal}")
    k = 2.0 / (signal + 1)
    seed_idx = valid_indices[signal - 1]
    seed_vals = [macd_line[i] for i in valid_indices[:signal]]
    sig_seed = sum(seed_vals) / signal  # type: ignore[arg-type]
    sig_series: list[float | None] = [None] * len(macd_line)
    sig_series[seed_idx] = sig_seed
    prev_sig = sig_seed
    for i in range(seed_idx + 1, len(macd_line)):
        v = macd_line[i]
        if v is None:
            sig_series[i] = None
        else:
            prev_sig = v * k + prev_sig * (1 - k)
            sig_series[i] = prev_sig
    macd_val = macd_line[-1]
    sig_val = sig_series[-1]
    hist = (macd_val - sig_val) if (macd_val is not None and sig_val is not None) else None
    return {
        "macd": macd_val,
        "signal": sig_val,
        "histogram": hist,
        "quality": _last_quality(bars),
        "fast": fast, "slow": slow, "signalPeriod": signal,
        "formula_version": FORMULA_VERSION["MACD"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# ATR — Average True Range (Wilder smoothing)
# ─────────────────────────────────────────────────────────────────────────────

def _true_ranges(bars: list[dict[str, Any]]) -> list[float]:
    trs = []
    for i, b in enumerate(bars):
        h, l, c = float(b["high"]), float(b["low"]), float(b["close"])
        if i == 0:
            trs.append(h - l)
        else:
            prev_c = float(bars[i - 1]["close"])
            trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return trs


def atr(bars: list[dict[str, Any]], period: int = 14) -> dict[str, Any]:
    """ATR using Wilder smoothing. No lookahead."""
    if not bars:
        return _unavail("no_bars")
    if len(bars) < period + 1:
        return _unavail(f"insufficient_bars:{len(bars)}<{period + 1}")
    trs = _true_ranges(bars)
    avg = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        avg = (avg * (period - 1) + trs[i]) / period
    return {"value": avg, "quality": _last_quality(bars), "period": period,
            "formula_version": FORMULA_VERSION["ATR"]}


# ─────────────────────────────────────────────────────────────────────────────
# ADX — Average Directional Index
# ─────────────────────────────────────────────────────────────────────────────

def adx(bars: list[dict[str, Any]], period: int = 14) -> dict[str, Any]:
    """ADX with +DI / -DI. No lookahead."""
    if not bars:
        return _unavail("no_bars")
    if len(bars) < period * 2 + 1:
        return _unavail(f"insufficient_bars:{len(bars)}<{period * 2 + 1}")
    trs = _true_ranges(bars)
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for i in range(1, len(bars)):
        up_move = float(bars[i]["high"]) - float(bars[i - 1]["high"])
        down_move = float(bars[i - 1]["low"]) - float(bars[i]["low"])
        pdm = up_move if (up_move > down_move and up_move > 0) else 0.0
        mdm = down_move if (down_move > up_move and down_move > 0) else 0.0
        plus_dm.append(pdm)
        minus_dm.append(mdm)
    # Wilder smoothing
    tr_s = sum(trs[1: period + 1])
    pdm_s = sum(plus_dm[:period])
    mdm_s = sum(minus_dm[:period])
    adx_list: list[float] = []
    for i in range(period, len(plus_dm)):
        tr_s = tr_s - tr_s / period + trs[i + 1]
        pdm_s = pdm_s - pdm_s / period + plus_dm[i]
        mdm_s = mdm_s - mdm_s / period + minus_dm[i]
        pdi = 100.0 * pdm_s / tr_s if tr_s != 0 else 0.0
        mdi = 100.0 * mdm_s / tr_s if tr_s != 0 else 0.0
        dxn = pdi + mdi
        dx = 100.0 * abs(pdi - mdi) / dxn if dxn != 0 else 0.0
        adx_list.append(dx)
    if len(adx_list) < period:
        return _unavail("insufficient_dx_values")
    adx_val = sum(adx_list[:period]) / period
    for i in range(period, len(adx_list)):
        adx_val = (adx_val * (period - 1) + adx_list[i]) / period
    # Final +DI / -DI
    tr_final = sum(trs[1: period + 1])
    pdm_final = sum(plus_dm[:period])
    mdm_final = sum(minus_dm[:period])
    for i in range(period, len(plus_dm)):
        tr_final = tr_final - tr_final / period + trs[i + 1]
        pdm_final = pdm_final - pdm_final / period + plus_dm[i]
        mdm_final = mdm_final - mdm_final / period + minus_dm[i]
    plus_di_val = 100.0 * pdm_final / tr_final if tr_final != 0 else 0.0
    minus_di_val = 100.0 * mdm_final / tr_final if tr_final != 0 else 0.0
    return {
        "adx": adx_val,
        "plusDI": plus_di_val,
        "minusDI": minus_di_val,
        "quality": _last_quality(bars),
        "period": period,
        "formula_version": FORMULA_VERSION["ADX"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Bollinger Bands
# ─────────────────────────────────────────────────────────────────────────────

def bollinger(bars: list[dict[str, Any]], period: int = 20, std_dev: float = 2.0) -> dict[str, Any]:
    """Bollinger Bands: middle=SMA, upper/lower=SMA ± k*σ."""
    if not bars:
        return _unavail("no_bars")
    closes = _closes(bars)
    n = len(closes)
    if n < period:
        return _unavail(f"insufficient_bars:{n}<{period}")
    window = closes[n - period:]
    mid = sum(window) / period
    variance = sum((x - mid) ** 2 for x in window) / period
    std = math.sqrt(variance)
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    last_close = closes[-1]
    bandwidth = (upper - lower) / mid if mid != 0 else None
    pct_b = (last_close - lower) / (upper - lower) if (upper - lower) != 0 else None
    return {
        "upper": upper,
        "middle": mid,
        "lower": lower,
        "bandwidth": bandwidth,
        "percentB": pct_b,
        "std": std,
        "quality": _last_quality(bars),
        "period": period,
        "stdDev": std_dev,
        "formula_version": FORMULA_VERSION["BOLLINGER"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# SuperTrend
# ─────────────────────────────────────────────────────────────────────────────

def supertrend(bars: list[dict[str, Any]], period: int = 10, multiplier: float = 3.0) -> dict[str, Any]:
    """SuperTrend indicator. No lookahead."""
    if not bars:
        return _unavail("no_bars")
    if len(bars) < period + 2:
        return _unavail(f"insufficient_bars:{len(bars)}<{period + 2}")
    trs = _true_ranges(bars)
    # Wilder ATR series
    atr_vals: list[float | None] = [None] * len(bars)
    atr_vals[period] = sum(trs[:period]) / period
    for i in range(period + 1, len(bars)):
        atr_vals[i] = (atr_vals[i - 1] * (period - 1) + trs[i]) / period  # type: ignore[operator]
    direction = 1  # 1 = uptrend, -1 = downtrend
    trend_val: float = 0.0
    upper_band: float = 0.0
    lower_band: float = 0.0
    prev_upper: float = 0.0
    prev_lower: float = 0.0
    prev_close: float = float(bars[period]["close"])
    for i in range(period, len(bars)):
        a = atr_vals[i]
        if a is None:
            continue
        hl2 = (float(bars[i]["high"]) + float(bars[i]["low"])) / 2.0
        basic_upper = hl2 + multiplier * a
        basic_lower = hl2 - multiplier * a
        final_upper = basic_upper if (basic_upper < prev_upper or prev_close > prev_upper) else prev_upper
        final_lower = basic_lower if (basic_lower > prev_lower or prev_close < prev_lower) else prev_lower
        c = float(bars[i]["close"])
        if direction == 1:
            if c < final_lower:
                direction = -1
                trend_val = final_upper
            else:
                trend_val = final_lower
        else:
            if c > final_upper:
                direction = 1
                trend_val = final_lower
            else:
                trend_val = final_upper
        upper_band = final_upper
        lower_band = final_lower
        prev_upper = final_upper
        prev_lower = final_lower
        prev_close = c
    label = "UPTREND" if direction == 1 else "DOWNTREND"
    return {
        "value": trend_val,
        "direction": direction,
        "label": label,
        "upperBand": upper_band,
        "lowerBand": lower_band,
        "quality": _last_quality(bars),
        "period": period,
        "multiplier": multiplier,
        "formula_version": FORMULA_VERSION["SUPERTREND"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Returns
# ─────────────────────────────────────────────────────────────────────────────

def returns(bars: list[dict[str, Any]], lookback: int = 1) -> dict[str, Any]:
    """Simple and log returns over `lookback` bars. No lookahead."""
    if not bars:
        return _unavail("no_bars")
    closes = _closes(bars)
    n = len(closes)
    if n < lookback + 1:
        return _unavail(f"insufficient_bars:{n}<{lookback + 1}")
    c_now = closes[-1]
    c_prev = closes[-(lookback + 1)]
    simple = (c_now / c_prev - 1.0) if c_prev != 0 else None
    log_ret = math.log(c_now / c_prev) if (c_prev != 0 and c_now > 0 and c_prev > 0) else None
    return {
        "simpleReturn": simple,
        "logReturn": log_ret,
        "lookback": lookback,
        "quality": _last_quality(bars),
        "formula_version": FORMULA_VERSION["RETURNS"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Realized Volatility
# ─────────────────────────────────────────────────────────────────────────────

def realized_vol(bars: list[dict[str, Any]], period: int = 20) -> dict[str, Any]:
    """Realized volatility: std dev of log returns × √period (annualised not applied)."""
    if not bars:
        return _unavail("no_bars")
    closes = _closes(bars)
    n = len(closes)
    if n < period + 1:
        return _unavail(f"insufficient_bars:{n}<{period + 1}")
    log_rets = []
    for i in range(n - period, n):
        c_prev = closes[i - 1]
        c_now = closes[i]
        if c_prev > 0 and c_now > 0:
            log_rets.append(math.log(c_now / c_prev))
    if len(log_rets) < 2:
        return _unavail("insufficient_log_returns")
    mean = sum(log_rets) / len(log_rets)
    variance = sum((r - mean) ** 2 for r in log_rets) / (len(log_rets) - 1)
    std = math.sqrt(variance)
    return {
        "value": std,
        "annualized": std * math.sqrt(365 * 24 * 12),  # assumes 5m bars; caller can adjust
        "period": period,
        "quality": _last_quality(bars),
        "formula_version": FORMULA_VERSION["REALIZED_VOL"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Volume Z-Score
# ─────────────────────────────────────────────────────────────────────────────

def volume_zscore(bars: list[dict[str, Any]], period: int = 20) -> dict[str, Any]:
    """Z-score of last bar's volume relative to rolling mean/std over `period` bars."""
    if not bars:
        return _unavail("no_bars")
    volumes = _volumes(bars)
    n = len(volumes)
    if n < period:
        return _unavail(f"insufficient_bars:{n}<{period}")
    window = volumes[n - period:]
    mean = sum(window) / period
    if period < 2:
        return _unavail("period_too_small")
    variance = sum((v - mean) ** 2 for v in window) / (period - 1)
    std = math.sqrt(variance) if variance > 0 else 0.0
    last_vol = volumes[-1]
    zscore = (last_vol - mean) / std if std > 0 else 0.0
    return {
        "value": zscore,
        "lastVolume": last_vol,
        "mean": mean,
        "std": std,
        "quality": _last_quality(bars),
        "period": period,
        "formula_version": FORMULA_VERSION["VOLUME_ZSCORE"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Price Distance from VWAP
# ─────────────────────────────────────────────────────────────────────────────

def price_dist_from_vwap(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Percentage distance of last close from cumulative VWAP."""
    if not bars:
        return _unavail("no_bars")
    vwap_result = vwap(bars)
    if vwap_result.get("value") is None:
        return _unavail(vwap_result.get("reason", "vwap_unavailable"))
    vwap_val: float = vwap_result["value"]
    last_close = float(bars[-1]["close"])
    dist_pct = (last_close - vwap_val) / vwap_val * 100.0 if vwap_val != 0 else None
    return {
        "value": dist_pct,
        "lastClose": last_close,
        "vwap": vwap_val,
        "quality": _last_quality(bars),
        "formula_version": FORMULA_VERSION["PRICE_DIST_VWAP"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Trend Slope (linear regression slope of close prices)
# ─────────────────────────────────────────────────────────────────────────────

def trend_slope(bars: list[dict[str, Any]], period: int = 20) -> dict[str, Any]:
    """Linear regression slope of close prices over `period` bars (normalised by mean)."""
    if not bars:
        return _unavail("no_bars")
    closes = _closes(bars)
    n = len(closes)
    if n < period:
        return _unavail(f"insufficient_bars:{n}<{period}")
    window = closes[n - period:]
    x_mean = (period - 1) / 2.0
    y_mean = sum(window) / period
    num = sum((i - x_mean) * (window[i] - y_mean) for i in range(period))
    denom = sum((i - x_mean) ** 2 for i in range(period))
    slope = num / denom if denom != 0 else 0.0
    norm_slope = slope / y_mean if y_mean != 0 else 0.0
    label = "UP" if norm_slope > 0.001 else ("DOWN" if norm_slope < -0.001 else "FLAT")
    return {
        "slope": slope,
        "normalizedSlope": norm_slope,
        "label": label,
        "quality": _last_quality(bars),
        "period": period,
        "formula_version": FORMULA_VERSION["TREND_SLOPE"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Composite: compute all indicators for a bar list
# ─────────────────────────────────────────────────────────────────────────────

def compute_all(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute all standard indicators at the last bar. No lookahead guaranteed."""
    return {
        "sma_20": sma(bars, 20),
        "sma_50": sma(bars, 50),
        "ema_20": ema(bars, 20),
        "ema_50": ema(bars, 50),
        "vwap": vwap(bars),
        "rsi_14": rsi(bars, 14),
        "macd": macd(bars),
        "atr_14": atr(bars, 14),
        "adx_14": adx(bars, 14),
        "bollinger_20": bollinger(bars, 20),
        "supertrend_10": supertrend(bars, 10),
        "returns_1": returns(bars, 1),
        "returns_5": returns(bars, 5),
        "realized_vol_20": realized_vol(bars, 20),
        "volume_zscore_20": volume_zscore(bars, 20),
        "price_dist_vwap": price_dist_from_vwap(bars),
        "trend_slope_20": trend_slope(bars, 20),
        "formula_versions": FORMULA_VERSION,
    }
