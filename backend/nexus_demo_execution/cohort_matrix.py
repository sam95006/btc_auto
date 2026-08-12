"""Strategy × regime × side cohort matrix and entry confirmations (offline)."""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from backend.nexus_demo_execution.historical_market_data import Candle
from backend.nexus_demo_execution.market_event_sim import _ohlc_dicts
from backend.nexus_demo_execution.market_structure import (
    atr_from_ohlc,
    support_resistance_from_swings,
    swing_high_low,
)
from backend.nexus_demo_execution.session_limits import TAKER_FEE_RATE_DEFAULT

COHORT_SPECS: list[tuple[str, str, str]] = [
    ("trend_following", "TRENDING_UP", "Buy"),
    ("trend_following", "TRENDING_DOWN", "Sell"),
    ("pullback", "TRENDING_UP", "Buy"),
    ("pullback", "TRENDING_DOWN", "Sell"),
    ("breakout", "BREAKOUT", "Buy"),
    ("breakout", "BREAKOUT", "Sell"),
    ("momentum", "HIGH_VOLATILITY", "Buy"),
    ("momentum", "HIGH_VOLATILITY", "Sell"),
    ("mean_reversion", "RANGE", "Buy"),
    ("mean_reversion", "RANGE", "Sell"),
    ("VWAP_reversion", "RANGE", "Buy"),
    ("VWAP_reversion", "RANGE", "Sell"),
    ("liquidity_sweep", "REVERSAL", "Buy"),
    ("liquidity_sweep", "REVERSAL", "Sell"),
    ("absorption_cvd_divergence", "REVERSAL", "Buy"),
    ("absorption_cvd_divergence", "REVERSAL", "Sell"),
    ("funding_oi_contrarian", "EXTREME_POSITIONING", "Buy"),
    ("funding_oi_contrarian", "EXTREME_POSITIONING", "Sell"),
    ("STRUCT_SWING", "RANGE", "Buy"),
    ("STRUCT_SWING", "RANGE", "Sell"),
]

DATA_UNAVAILABLE_STRATEGIES = frozenset(
    {
        "absorption_cvd_divergence",
        "funding_oi_contrarian",
    }
)

MIN_EXPECTED_MOVE_COST_MULT = 1.8
MAX_SPREAD_BPS_RESEARCH = 8.0
MAX_SLIPPAGE_BPS_RESEARCH = 8.0
SL_COOLDOWN_BARS = 8
SAME_SYMBOL_REENTRY_COOLDOWN_BARS = 6
DUPLICATE_DIRECTION_SUPPRESS = True
MIN_SAMPLE_REPLAY = 20
MIN_SAMPLE_FOLD = 8


@dataclass
class MarketContext:
    closes: list[float]
    volumes: list[float]
    atr: float | None
    atr_median: float | None
    swing_high: float | None
    swing_low: float | None
    support: float | None
    resistance: float | None
    sma20: float | None
    sma50: float | None
    vwap_proxy: float | None
    last: Candle
    regime_labels: set[str]


def _sma(xs: list[float], n: int) -> float | None:
    if len(xs) < n:
        return None
    return sum(xs[-n:]) / float(n)


def classify_regimes(hist: list[Candle], atr: float | None) -> set[str]:
    closes = [c.close for c in hist]
    labels: set[str] = set()
    if len(closes) < 30:
        labels.add("UNKNOWN")
        return labels
    sma20 = _sma(closes, 20) or closes[-1]
    sma50 = _sma(closes, 50) or sma20
    last = closes[-1]
    if last > sma20 * 1.003 and sma20 >= sma50 * 0.999:
        labels.add("TRENDING_UP")
        labels.add("TREND_UP")
    elif last < sma20 * 0.997 and sma20 <= sma50 * 1.001:
        labels.add("TRENDING_DOWN")
        labels.add("TREND_DOWN")
    else:
        labels.add("RANGE")
    if atr is not None and last > 0:
        atr_pct = atr / last
        recent_ranges = [(c.high - c.low) / c.close for c in hist[-20:] if c.close > 0]
        med = statistics.median(recent_ranges) if recent_ranges else atr_pct
        if atr_pct > med * 1.35:
            labels.add("HIGH_VOLATILITY")
    prior = hist[-21:-1]
    if prior:
        ph = max(c.high for c in prior)
        pl = min(c.low for c in prior)
        vol_med = statistics.median([c.volume for c in prior]) if prior else 0.0
        vol_ok = hist[-1].volume > vol_med * 1.2 if vol_med > 0 else True
        if last > ph and vol_ok:
            labels.add("BREAKOUT")
        if last < pl and vol_ok:
            labels.add("BREAKOUT")
    sh = max(c.high for c in hist[-15:])
    sl = min(c.low for c in hist[-15:])
    bar = hist[-1]
    if bar.low < sl * 1.0001 and bar.close > sl and bar.close > bar.open:
        labels.add("REVERSAL")
    if bar.high > sh * 0.9999 and bar.close < sh and bar.close < bar.open:
        labels.add("REVERSAL")
    return labels


def build_context(hist: list[Candle], atr_period: int = 14, swing_lookback: int = 20) -> MarketContext:
    ohlc = _ohlc_dicts(hist)
    atr = atr_from_ohlc(ohlc, period=atr_period)
    sh, sl = swing_high_low(ohlc, lookback=swing_lookback)
    last = hist[-1]
    support, resistance = support_resistance_from_swings(last=last.close, swing_high=sh, swing_low=sl)
    closes = [c.close for c in hist]
    vols = [c.volume for c in hist]
    ranges = [(c.high - c.low) for c in hist[-40:] if c.close > 0]
    atr_med = statistics.median(ranges) if ranges else None
    window = hist[-48:]
    num = sum(((c.high + c.low + c.close) / 3.0) * c.volume for c in window)
    den = sum(c.volume for c in window) or 1.0
    labels = classify_regimes(hist, atr)
    return MarketContext(
        closes=closes,
        volumes=vols,
        atr=atr,
        atr_median=atr_med,
        swing_high=sh,
        swing_low=sl,
        support=support,
        resistance=resistance,
        sma20=_sma(closes, 20),
        sma50=_sma(closes, 50),
        vwap_proxy=num / den,
        last=last,
        regime_labels=labels,
    )


def _momentum_ok(closes: list[float], side: str) -> bool:
    if len(closes) < 6:
        return False
    delta = closes[-1] - closes[-5]
    return delta > 0 if side == "Buy" else delta < 0


def confirm_entry(strategy: str, regime: str, side: str, ctx: MarketContext) -> tuple[bool, str]:
    if strategy in DATA_UNAVAILABLE_STRATEGIES:
        return False, "DATA_UNAVAILABLE"
    if regime not in ctx.regime_labels and not (
        strategy == "STRUCT_SWING" and regime == "RANGE" and "RANGE" in ctx.regime_labels
    ):
        return False, "REGIME_MISMATCH"
    last = ctx.last.close
    atr = ctx.atr or 0.0

    if strategy == "trend_following":
        if side == "Buy" and "TRENDING_UP" not in ctx.regime_labels:
            return False, "TREND_NOT_CONFIRMED"
        if side == "Sell" and "TRENDING_DOWN" not in ctx.regime_labels:
            return False, "TREND_NOT_CONFIRMED"
        if not _momentum_ok(ctx.closes, side):
            return False, "MOMENTUM_MISSING"
        if side == "Buy" and ctx.resistance and last > ctx.resistance * 0.998:
            return False, "RESISTANCE_CONFLICT"
        if side == "Sell" and ctx.support and last < ctx.support * 1.002:
            return False, "SUPPORT_CONFLICT"
        if atr <= 0 or atr / last < 0.0015:
            return False, "EXPECTED_MOVE_TOO_SMALL"
        return True, "OK"

    if strategy == "pullback":
        if side == "Buy" and "TRENDING_UP" not in ctx.regime_labels:
            return False, "TREND_INVALID"
        if side == "Sell" and "TRENDING_DOWN" not in ctx.regime_labels:
            return False, "TREND_INVALID"
        if ctx.sma20 is None:
            return False, "SMA_MISSING"
        dist = abs(last - ctx.sma20) / last
        if dist > 0.012:
            return False, "RETRACEMENT_TOO_DEEP"
        if side == "Buy" and last > ctx.sma20 * 1.004:
            return False, "NO_PULLBACK"
        if side == "Sell" and last < ctx.sma20 * 0.996:
            return False, "NO_PULLBACK"
        if side == "Buy" and ctx.last.close <= ctx.last.open:
            return False, "NO_RECLAIM"
        if side == "Sell" and ctx.last.close >= ctx.last.open:
            return False, "NO_RECLAIM"
        return True, "OK"

    if strategy == "breakout":
        if "BREAKOUT" not in ctx.regime_labels:
            return False, "NO_BREAKOUT"
        if side == "Buy" and ctx.swing_high and atr > 0 and last > ctx.swing_high + 1.5 * atr:
            return False, "OVEREXTENDED"
        if side == "Sell" and ctx.swing_low and atr > 0 and last < ctx.swing_low - 1.5 * atr:
            return False, "OVEREXTENDED"
        return True, "OK"

    if strategy == "momentum":
        if "HIGH_VOLATILITY" not in ctx.regime_labels:
            return False, "VOL_NOT_HIGH"
        if not _momentum_ok(ctx.closes, side):
            return False, "MOMENTUM_MISSING"
        return True, "OK"

    if strategy == "mean_reversion":
        if "RANGE" not in ctx.regime_labels:
            return False, "NOT_RANGE"
        if "BREAKOUT" in ctx.regime_labels:
            return False, "BREAKOUT_EXPANSION"
        if ctx.sma20 is None:
            return False, "MEAN_MISSING"
        if side == "Buy" and last >= ctx.sma20:
            return False, "NOT_NEAR_LOWER_BOUNDARY"
        if side == "Sell" and last <= ctx.sma20:
            return False, "NOT_NEAR_UPPER_BOUNDARY"
        if ctx.support and side == "Buy" and last > ctx.support * 1.008:
            return False, "NOT_NEAR_SUPPORT"
        if ctx.resistance and side == "Sell" and last < ctx.resistance * 0.992:
            return False, "NOT_NEAR_RESISTANCE"
        return True, "OK"

    if strategy == "VWAP_reversion":
        if "RANGE" not in ctx.regime_labels:
            return False, "NOT_RANGE"
        if ctx.vwap_proxy is None:
            return False, "VWAP_MISSING"
        dist = (last - ctx.vwap_proxy) / last
        if side == "Buy" and dist > -0.002:
            return False, "NOT_BELOW_VWAP"
        if side == "Sell" and dist < 0.002:
            return False, "NOT_ABOVE_VWAP"
        if "BREAKOUT" in ctx.regime_labels:
            return False, "BREAKOUT_EXPANSION"
        return True, "OK"

    if strategy == "liquidity_sweep":
        if "REVERSAL" not in ctx.regime_labels:
            return False, "NO_SWEEP_RECLAIM"
        if side == "Buy" and ctx.last.close <= ctx.last.open:
            return False, "NO_REJECTION_UP"
        if side == "Sell" and ctx.last.close >= ctx.last.open:
            return False, "NO_REJECTION_DOWN"
        return True, "OK"

    if strategy == "STRUCT_SWING":
        if "RANGE" not in ctx.regime_labels:
            return False, "BASELINE_RANGE_ONLY"
        return True, "BASELINE_GEOMETRY_ONLY"

    return False, "UNKNOWN_STRATEGY"


def churn_prefilter(ctx: MarketContext, *, spread_bps: float, slip_bps: float) -> tuple[bool, str]:
    if spread_bps > MAX_SPREAD_BPS_RESEARCH:
        return False, "SPREAD_BUCKET_HIGH"
    if slip_bps > MAX_SLIPPAGE_BPS_RESEARCH:
        return False, "SLIPPAGE_BUCKET_HIGH"
    atr = ctx.atr or 0.0
    last = ctx.last.close
    if atr <= 0 or last <= 0:
        return False, "ATR_MISSING"
    expected_move = 1.2 * atr
    notional = 500.0
    cost = notional * (2 * TAKER_FEE_RATE_DEFAULT + (spread_bps + slip_bps) / 10000.0)
    move_value = (expected_move / last) * notional
    if move_value < cost * MIN_EXPECTED_MOVE_COST_MULT:
        return False, "EXPECTED_MOVE_AFTER_COST_TOO_SMALL"
    return True, "OK"


def cohort_key(strategy: str, regime: str, side: str) -> str:
    return f"{strategy}|{regime}|{side}"
