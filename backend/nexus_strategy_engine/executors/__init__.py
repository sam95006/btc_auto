"""Per-component deterministic executors — no silent family fallback."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from backend.nexus_demo_execution.historical_market_data import Candle
from backend.nexus_strategy_engine.components import COMPONENT_IDS
from backend.nexus_strategy_engine.strategy_spec import sha_obj


@dataclass
class ExecutorSignal:
    side: str
    regime: str
    entry_index: int
    entry_price: float
    stop_price: float
    target_price: float
    stop_basis: str
    target_basis: str
    event_id: str
    confirmation: str
    late_entry_rejected: bool = False
    funnel: dict[str, int] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScanContext:
    symbol: str
    candles_15: list[Candle]
    candles_60: list[Candle] | None = None
    candles_240: list[Candle] | None = None
    funding_points: list[dict[str, Any]] | None = None
    oi_points: list[dict[str, Any]] | None = None
    mark_candles: list[Candle] | None = None
    index_candles: list[Candle] | None = None
    peer_returns_at_ts: dict[str, float] | None = None  # for cross-sectional
    btc_return_at_ts: float | None = None


def atr(candles: list[Candle], i: int, n: int = 14) -> float | None:
    if i < n or i >= len(candles):
        return None
    trs = []
    for j in range(i - n + 1, i + 1):
        c = candles[j]
        prev = candles[j - 1]
        trs.append(max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close)))
    return sum(trs) / len(trs) if trs else None


def asof_index(candles: list[Candle] | None, ts_ms: int) -> int | None:
    if not candles:
        return None
    lo, hi, best = 0, len(candles) - 1, -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if candles[mid].ts_ms <= ts_ms:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best if best >= 0 else None


def lookup_series(points: list[dict[str, Any]] | None, ts_ms: int, key: str) -> float | None:
    if not points:
        return None
    best = None
    for p in points:
        t = int(p.get("ts_ms") or 0)
        if t <= ts_ms:
            best = p
        else:
            break
    if best is None or best.get(key) is None:
        return None
    return float(best[key])


class ComponentExecutor:
    component_id: str
    implemented: bool = True
    required_capabilities: tuple[str, ...] = ("PRICE_HISTORY_ELIGIBLE",)

    def checksum(self) -> str:
        return sha_obj(
            {
                "component_id": self.component_id,
                "implemented": self.implemented,
                "required_capabilities": list(self.required_capabilities),
                "class": self.__class__.__name__,
            }
        )

    def scan(self, ctx: ScanContext, *, stride: int = 16, cooldown: int = 24) -> list[ExecutorSignal]:
        raise NotImplementedError


class NotImplementedExecutor(ComponentExecutor):
    implemented = False

    def __init__(self, component_id: str):
        self.component_id = component_id

    def scan(self, ctx: ScanContext, *, stride: int = 16, cooldown: int = 24) -> list[ExecutorSignal]:
        return []


class TrendContinuationExecutor(ComponentExecutor):
    component_id = "TREND_CONTINUATION"

    def scan(self, ctx: ScanContext, *, stride: int = 16, cooldown: int = 24) -> list[ExecutorSignal]:
        out: list[ExecutorSignal] = []
        c15 = ctx.candles_15
        last = -10_000
        for i in range(80, len(c15) - 8, stride):
            if i - last < cooldown:
                continue
            a = atr(c15, i)
            if a is None:
                continue
            # Context: 60m trend direction if available
            ts = c15[i].ts_ms
            i60 = asof_index(ctx.candles_60, ts)
            if i60 is None or i60 < 20:
                continue  # multi-TF required for this executor
            slope = (ctx.candles_60[i60].close - ctx.candles_60[i60 - 10].close) / max(
                ctx.candles_60[i60 - 10].close, 1e-9
            )
            # Event: pullback then resume in trend direction
            if slope > 0.015:
                pullback = c15[i].low <= min(x.low for x in c15[i - 5 : i]) and c15[i].close > c15[i - 1].close
                if not pullback:
                    continue
                # Late entry: extension too far from 60m close
                if abs(c15[i].close - ctx.candles_60[i60].close) / max(a, 1e-9) > 1.5:
                    continue
                side, regime = "Buy", "TRENDING_UP"
                stop = min(x.low for x in c15[i - 5 : i + 1]) - 0.2 * a
                target = c15[i].close + 2.5 * a
                stop_basis, target_basis = "pullback_swing_invalidation", "atr_continuation_2_5"
            elif slope < -0.015:
                pullback = c15[i].high >= max(x.high for x in c15[i - 5 : i]) and c15[i].close < c15[i - 1].close
                if not pullback:
                    continue
                if abs(c15[i].close - ctx.candles_60[i60].close) / max(a, 1e-9) > 1.5:
                    continue
                side, regime = "Sell", "TRENDING_DOWN"
                stop = max(x.high for x in c15[i - 5 : i + 1]) + 0.2 * a
                target = c15[i].close - 2.5 * a
                stop_basis, target_basis = "pullback_swing_invalidation", "atr_continuation_2_5"
            else:
                continue
            out.append(
                ExecutorSignal(
                    side=side,
                    regime=regime,
                    entry_index=i,
                    entry_price=float(c15[i].close),
                    stop_price=float(stop),
                    target_price=float(target),
                    stop_basis=stop_basis,
                    target_basis=target_basis,
                    event_id="trend_pullback_resume",
                    confirmation="close_resumes_with_60m_slope",
                )
            )
            last = i
        return out


class StructuralRetestExecutor(ComponentExecutor):
    component_id = "STRUCTURAL_RETEST"

    def scan(self, ctx: ScanContext, *, stride: int = 16, cooldown: int = 20) -> list[ExecutorSignal]:
        out: list[ExecutorSignal] = []
        c15 = ctx.candles_15
        last = -10_000
        for i in range(60, len(c15) - 8, stride):
            if i - last < cooldown:
                continue
            a = atr(c15, i)
            if a is None:
                continue
            level_high = max(x.high for x in c15[i - 30 : i - 5])
            level_low = min(x.low for x in c15[i - 30 : i - 5])
            # Break then retest
            broke_up = any(x.close > level_high for x in c15[i - 5 : i]) and abs(c15[i].low - level_high) <= 0.4 * a
            broke_dn = any(x.close < level_low for x in c15[i - 5 : i]) and abs(c15[i].high - level_low) <= 0.4 * a
            if broke_up and c15[i].close > level_high:
                stop = level_high - 0.5 * a
                target = c15[i].close + (level_high - level_low)
                out.append(
                    ExecutorSignal(
                        side="Buy",
                        regime="TRENDING_UP",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(stop),
                        target_price=float(target),
                        stop_basis="broken_level_invalidation",
                        target_basis="measured_range_height",
                        event_id="structural_retest_long",
                        confirmation="close_holds_above_broken_level",
                    )
                )
                last = i
            elif broke_dn and c15[i].close < level_low:
                stop = level_low + 0.5 * a
                target = c15[i].close - (level_high - level_low)
                out.append(
                    ExecutorSignal(
                        side="Sell",
                        regime="TRENDING_DOWN",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(stop),
                        target_price=float(target),
                        stop_basis="broken_level_invalidation",
                        target_basis="measured_range_height",
                        event_id="structural_retest_short",
                        confirmation="close_holds_below_broken_level",
                    )
                )
                last = i
        return out


class BreakoutExecutor(ComponentExecutor):
    component_id = "BREAKOUT"

    def scan(self, ctx: ScanContext, *, stride: int = 12, cooldown: int = 30) -> list[ExecutorSignal]:
        out: list[ExecutorSignal] = []
        c15 = ctx.candles_15
        last = -10_000
        for i in range(50, len(c15) - 8, stride):
            if i - last < cooldown:
                continue
            window = c15[i - 24 : i]
            hi = max(x.high for x in window)
            lo = min(x.low for x in window)
            height = hi - lo
            if height <= 0:
                continue
            vol_exp = c15[i].volume > 1.5 * (sum(x.volume for x in window) / len(window))
            if c15[i].close > hi and vol_exp:
                # late entry if already extended > 30% of range
                if c15[i].close > hi + 0.3 * height:
                    continue
                out.append(
                    ExecutorSignal(
                        side="Buy",
                        regime="VOL_EXPAND",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(hi - 0.25 * height),  # range re-entry invalidation
                        target_price=float(hi + height),
                        stop_basis="range_reentry_invalidation",
                        target_basis="measured_move_range_height",
                        event_id="range_breakout_up",
                        confirmation="volume_expansion_close_above_range",
                    )
                )
                last = i
            elif c15[i].close < lo and vol_exp:
                if c15[i].close < lo - 0.3 * height:
                    continue
                out.append(
                    ExecutorSignal(
                        side="Sell",
                        regime="VOL_EXPAND",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(lo + 0.25 * height),
                        target_price=float(lo - height),
                        stop_basis="range_reentry_invalidation",
                        target_basis="measured_move_range_height",
                        event_id="range_breakout_down",
                        confirmation="volume_expansion_close_below_range",
                    )
                )
                last = i
        return out


class FailedBreakoutExecutor(ComponentExecutor):
    component_id = "FAILED_BREAKOUT"

    def scan(self, ctx: ScanContext, *, stride: int = 12, cooldown: int = 28) -> list[ExecutorSignal]:
        out: list[ExecutorSignal] = []
        c15 = ctx.candles_15
        last = -10_000
        for i in range(50, len(c15) - 8, stride):
            if i - last < cooldown:
                continue
            window = c15[i - 24 : i - 3]
            hi = max(x.high for x in window)
            lo = min(x.low for x in window)
            mid = (hi + lo) / 2
            # Sweep above then reclaim below
            if any(x.high > hi for x in c15[i - 3 : i]) and c15[i].close < hi:
                out.append(
                    ExecutorSignal(
                        side="Sell",
                        regime="RANGE",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(max(x.high for x in c15[i - 3 : i + 1])),
                        target_price=float(mid),
                        stop_basis="failed_extreme_invalidation",
                        target_basis="range_midpoint",
                        event_id="failed_breakout_short",
                        confirmation="close_reclaims_inside_range",
                    )
                )
                last = i
            elif any(x.low < lo for x in c15[i - 3 : i]) and c15[i].close > lo:
                out.append(
                    ExecutorSignal(
                        side="Buy",
                        regime="RANGE",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(min(x.low for x in c15[i - 3 : i + 1])),
                        target_price=float(mid),
                        stop_basis="failed_extreme_invalidation",
                        target_basis="range_midpoint",
                        event_id="failed_breakout_long",
                        confirmation="close_reclaims_inside_range",
                    )
                )
                last = i
        return out


class MomentumAccelerationExecutor(ComponentExecutor):
    component_id = "MOMENTUM_ACCELERATION"

    def scan(self, ctx: ScanContext, *, stride: int = 10, cooldown: int = 18) -> list[ExecutorSignal]:
        out: list[ExecutorSignal] = []
        c15 = ctx.candles_15
        last = -10_000
        for i in range(40, len(c15) - 8, stride):
            if i - last < cooldown:
                continue
            a = atr(c15, i)
            a_prev = atr(c15, i - 5)
            if a is None or a_prev is None or a_prev <= 0:
                continue
            accel = a / a_prev
            ret3 = (c15[i].close - c15[i - 3].close) / max(c15[i - 3].close, 1e-9)
            if accel < 1.35:
                continue
            if ret3 > 0.012:
                out.append(
                    ExecutorSignal(
                        side="Buy",
                        regime="VOL_EXPAND",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(c15[i].close - 1.0 * a),
                        target_price=float(c15[i].close + 2.8 * a),
                        stop_basis="atr_thrust_invalidation_1_0",
                        target_basis="atr_thrust_target_2_8",
                        event_id="momentum_accel_long",
                        confirmation="atr_acceleration_with_positive_thrust",
                    )
                )
                last = i
            elif ret3 < -0.012:
                out.append(
                    ExecutorSignal(
                        side="Sell",
                        regime="VOL_EXPAND",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(c15[i].close + 1.0 * a),
                        target_price=float(c15[i].close - 2.8 * a),
                        stop_basis="atr_thrust_invalidation_1_0",
                        target_basis="atr_thrust_target_2_8",
                        event_id="momentum_accel_short",
                        confirmation="atr_acceleration_with_negative_thrust",
                    )
                )
                last = i
        return out


class VolatilityExpansionExecutor(ComponentExecutor):
    component_id = "VOLATILITY_EXPANSION"

    def scan(self, ctx: ScanContext, *, stride: int = 14, cooldown: int = 40) -> list[ExecutorSignal]:
        out: list[ExecutorSignal] = []
        c15 = ctx.candles_15
        last = -10_000
        for i in range(80, len(c15) - 8, stride):
            if i - last < cooldown:
                continue
            a = atr(c15, i)
            hist = [atr(c15, j) for j in range(i - 40, i) if atr(c15, j)]
            if a is None or len(hist) < 20:
                continue
            hist_sorted = sorted(hist)
            p80 = hist_sorted[int(0.8 * (len(hist_sorted) - 1))]
            p20 = hist_sorted[int(0.2 * (len(hist_sorted) - 1))]
            # Expansion from compression
            if hist[-1] and hist[-1] > p20 * 0.9 and a >= p80 and hist[0] and min(hist[:10]) <= p20:
                direction = 1 if c15[i].close > c15[i - 1].close else -1
                side = "Buy" if direction > 0 else "Sell"
                stop = c15[i].close - 1.6 * a if side == "Buy" else c15[i].close + 1.6 * a
                target = c15[i].close + 2.2 * a if side == "Buy" else c15[i].close - 2.2 * a
                out.append(
                    ExecutorSignal(
                        side=side,
                        regime="VOL_EXPAND",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(stop),
                        target_price=float(target),
                        stop_basis="atr_percentile_invalidation_1_6",
                        target_basis="vol_expansion_target_2_2",
                        event_id="volatility_expansion_break",
                        confirmation="atr_crosses_80th_after_compression",
                    )
                )
                last = i
        return out


class VwapMeanReversionExecutor(ComponentExecutor):
    component_id = "VWAP_MEAN_REVERSION"

    def scan(self, ctx: ScanContext, *, stride: int = 12, cooldown: int = 16) -> list[ExecutorSignal]:
        out: list[ExecutorSignal] = []
        c15 = ctx.candles_15
        last = -10_000
        for i in range(48, len(c15) - 8, stride):
            if i - last < cooldown:
                continue
            a = atr(c15, i)
            if a is None:
                continue
            # Session-like VWAP over last 32 bars
            num = sum(((x.high + x.low + x.close) / 3) * x.volume for x in c15[i - 32 : i + 1])
            den = sum(x.volume for x in c15[i - 32 : i + 1]) or 1e-9
            vwap = num / den
            # Require non-trend 60m if present
            i60 = asof_index(ctx.candles_60, c15[i].ts_ms)
            if i60 is not None and i60 >= 10:
                slope = abs(
                    (ctx.candles_60[i60].close - ctx.candles_60[i60 - 8].close)
                    / max(ctx.candles_60[i60 - 8].close, 1e-9)
                )
                if slope > 0.02:
                    continue
            dist = c15[i].close - vwap
            if dist > 1.8 * a:
                out.append(
                    ExecutorSignal(
                        side="Sell",
                        regime="RANGE",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(c15[i].close + 1.0 * a),
                        target_price=float(vwap),
                        stop_basis="extension_invalidation_1_0atr",
                        target_basis="vwap_mean",
                        event_id="vwap_fade_short",
                        confirmation="close_stretched_above_vwap_nontrend",
                    )
                )
                last = i
            elif dist < -1.8 * a:
                out.append(
                    ExecutorSignal(
                        side="Buy",
                        regime="RANGE",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(c15[i].close - 1.0 * a),
                        target_price=float(vwap),
                        stop_basis="extension_invalidation_1_0atr",
                        target_basis="vwap_mean",
                        event_id="vwap_fade_long",
                        confirmation="close_stretched_below_vwap_nontrend",
                    )
                )
                last = i
        return out


class StructuralMeanReversionExecutor(ComponentExecutor):
    component_id = "STRUCTURAL_MEAN_REVERSION"

    def scan(self, ctx: ScanContext, *, stride: int = 12, cooldown: int = 20) -> list[ExecutorSignal]:
        out: list[ExecutorSignal] = []
        c15 = ctx.candles_15
        last = -10_000
        for i in range(40, len(c15) - 8, stride):
            if i - last < cooldown:
                continue
            a = atr(c15, i)
            if a is None:
                continue
            hi = max(x.high for x in c15[i - 36 : i])
            lo = min(x.low for x in c15[i - 36 : i])
            mid = (hi + lo) / 2
            if c15[i].high >= hi and c15[i].close < hi - 0.1 * a:
                out.append(
                    ExecutorSignal(
                        side="Sell",
                        regime="RANGE",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(hi + 0.3 * a),
                        target_price=float(mid),
                        stop_basis="outside_range_invalidation",
                        target_basis="structural_range_mid",
                        event_id="range_extreme_fade_short",
                        confirmation="wick_rejects_range_high",
                    )
                )
                last = i
            elif c15[i].low <= lo and c15[i].close > lo + 0.1 * a:
                out.append(
                    ExecutorSignal(
                        side="Buy",
                        regime="RANGE",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(lo - 0.3 * a),
                        target_price=float(mid),
                        stop_basis="outside_range_invalidation",
                        target_basis="structural_range_mid",
                        event_id="range_extreme_fade_long",
                        confirmation="wick_rejects_range_low",
                    )
                )
                last = i
        return out


class RelativeStrengthExecutor(ComponentExecutor):
    component_id = "RELATIVE_STRENGTH"
    required_capabilities = ("PRICE_HISTORY_ELIGIBLE",)

    def scan(self, ctx: ScanContext, *, stride: int = 20, cooldown: int = 32) -> list[ExecutorSignal]:
        out: list[ExecutorSignal] = []
        if not ctx.peer_returns_at_ts or ctx.btc_return_at_ts is None:
            return out  # must be driven by cross-sectional engine
        c15 = ctx.candles_15
        # Use last bar only when ranking context present for that bar's ts
        i = len(c15) - 10
        if i < 40:
            return out
        a = atr(c15, i)
        if a is None:
            return out
        peers = ctx.peer_returns_at_ts
        ranks = sorted(peers.items(), key=lambda kv: kv[1], reverse=True)
        if not ranks:
            return out
        n = len(ranks)
        long_cut = max(1, int(0.2 * n))
        short_cut = max(1, int(0.2 * n))
        long_bucket = {s for s, _ in ranks[:long_cut]}
        short_bucket = {s for s, _ in ranks[-short_cut:]}
        my_ret = peers.get(ctx.symbol)
        if my_ret is None:
            return out
        rank_pos = [s for s, _ in ranks].index(ctx.symbol) if ctx.symbol in peers else -1
        percentile = 1.0 - (rank_pos / max(n - 1, 1)) if rank_pos >= 0 else 0.5
        if ctx.symbol in long_bucket and my_ret > ctx.btc_return_at_ts:
            out.append(
                ExecutorSignal(
                    side="Buy",
                    regime="TRENDING_UP",
                    entry_index=i,
                    entry_price=float(c15[i].close),
                    stop_price=float(c15[i].close - 1.3 * a),
                    target_price=float(c15[i].close + 2.0 * a),
                    stop_basis="rs_atr_invalidation",
                    target_basis="rs_atr_target",
                    event_id="relative_strength_long_bucket",
                    confirmation="top_quintile_vs_btc",
                    extras={
                        "ranking_feature": "ret_16bar",
                        "rank_percentile": percentile,
                        "long_bucket": sorted(long_bucket),
                        "short_bucket": sorted(short_bucket),
                        "benchmark_reference": "BTCUSDT",
                    },
                )
            )
        elif ctx.symbol in short_bucket and my_ret < ctx.btc_return_at_ts:
            out.append(
                ExecutorSignal(
                    side="Sell",
                    regime="TRENDING_DOWN",
                    entry_index=i,
                    entry_price=float(c15[i].close),
                    stop_price=float(c15[i].close + 1.3 * a),
                    target_price=float(c15[i].close - 2.0 * a),
                    stop_basis="rs_atr_invalidation",
                    target_basis="rs_atr_target",
                    event_id="relative_strength_short_bucket",
                    confirmation="bottom_quintile_vs_btc",
                    extras={
                        "ranking_feature": "ret_16bar",
                        "rank_percentile": percentile,
                        "long_bucket": sorted(long_bucket),
                        "short_bucket": sorted(short_bucket),
                        "benchmark_reference": "BTCUSDT",
                    },
                )
            )
        return out


class CrossSectionalMomentumExecutor(ComponentExecutor):
    component_id = "CROSS_SECTIONAL_MOMENTUM"

    def scan(self, ctx: ScanContext, *, stride: int = 20, cooldown: int = 32) -> list[ExecutorSignal]:
        # Same ranking substrate as RS but uses absolute cross-sectional momentum buckets
        out: list[ExecutorSignal] = []
        if not ctx.peer_returns_at_ts:
            return out
        c15 = ctx.candles_15
        i = len(c15) - 10
        if i < 40:
            return out
        a = atr(c15, i)
        if a is None:
            return out
        ranks = sorted(ctx.peer_returns_at_ts.items(), key=lambda kv: kv[1], reverse=True)
        n = len(ranks)
        long_bucket = {s for s, _ in ranks[: max(1, int(0.2 * n))]}
        short_bucket = {s for s, _ in ranks[-max(1, int(0.2 * n)) :]}
        if ctx.symbol in long_bucket:
            out.append(
                ExecutorSignal(
                    side="Buy",
                    regime="TRENDING_UP",
                    entry_index=i,
                    entry_price=float(c15[i].close),
                    stop_price=float(c15[i].close - 1.25 * a),
                    target_price=float(c15[i].close + 2.1 * a),
                    stop_basis="xs_mom_invalidation",
                    target_basis="xs_mom_target",
                    event_id="xs_momentum_long",
                    confirmation="cross_sectional_top_bucket",
                    extras={"rebalance_rule": "snapshot_rank_at_decision", "survivorship_protection": True},
                )
            )
        elif ctx.symbol in short_bucket:
            out.append(
                ExecutorSignal(
                    side="Sell",
                    regime="TRENDING_DOWN",
                    entry_index=i,
                    entry_price=float(c15[i].close),
                    stop_price=float(c15[i].close + 1.25 * a),
                    target_price=float(c15[i].close - 2.1 * a),
                    stop_basis="xs_mom_invalidation",
                    target_basis="xs_mom_target",
                    event_id="xs_momentum_short",
                    confirmation="cross_sectional_bottom_bucket",
                    extras={"rebalance_rule": "snapshot_rank_at_decision", "survivorship_protection": True},
                )
            )
        return out


class LiquiditySweepExecutor(ComponentExecutor):
    component_id = "LIQUIDITY_SWEEP_REVERSAL"

    def scan(self, ctx: ScanContext, *, stride: int = 10, cooldown: int = 22) -> list[ExecutorSignal]:
        out: list[ExecutorSignal] = []
        c15 = ctx.candles_15
        last = -10_000
        for i in range(40, len(c15) - 8, stride):
            if i - last < cooldown:
                continue
            a = atr(c15, i)
            if a is None:
                continue
            prior_low = min(x.low for x in c15[i - 20 : i - 1])
            prior_high = max(x.high for x in c15[i - 20 : i - 1])
            # Sweep low then reclaim
            if c15[i - 1].low < prior_low and c15[i].close > prior_low:
                out.append(
                    ExecutorSignal(
                        side="Buy",
                        regime="RANGE",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(c15[i - 1].low - 0.1 * a),
                        target_price=float(prior_high),
                        stop_basis="sweep_extreme_invalidation",
                        target_basis="opposite_liquidity",
                        event_id="liquidity_sweep_long",
                        confirmation="reclaim_after_low_sweep",
                    )
                )
                last = i
            elif c15[i - 1].high > prior_high and c15[i].close < prior_high:
                out.append(
                    ExecutorSignal(
                        side="Sell",
                        regime="RANGE",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(c15[i - 1].high + 0.1 * a),
                        target_price=float(prior_low),
                        stop_basis="sweep_extreme_invalidation",
                        target_basis="opposite_liquidity",
                        event_id="liquidity_sweep_short",
                        confirmation="reclaim_after_high_sweep",
                    )
                )
                last = i
        return out


class FundingOiContinuationExecutor(ComponentExecutor):
    component_id = "FUNDING_OI_CONTINUATION"
    required_capabilities = ("DERIVATIVES_HISTORY_ELIGIBLE", "PRICE_HISTORY_ELIGIBLE")

    def scan(self, ctx: ScanContext, *, stride: int = 20, cooldown: int = 36) -> list[ExecutorSignal]:
        out: list[ExecutorSignal] = []
        if not ctx.funding_points or not ctx.oi_points:
            return out  # missing → caller marks INELIGIBLE, no price proxy
        c15 = ctx.candles_15
        last = -10_000
        for i in range(40, len(c15) - 8, stride):
            if i - last < cooldown:
                continue
            ts = c15[i].ts_ms
            fr = lookup_series(ctx.funding_points, ts, "funding_rate")
            oi = lookup_series(ctx.oi_points, ts, "open_interest")
            oi_prev = lookup_series(ctx.oi_points, ts - 8 * 3_600_000, "open_interest")
            if fr is None or oi is None or oi_prev is None or oi_prev <= 0:
                continue
            oi_chg = (oi - oi_prev) / oi_prev
            a = atr(c15, i)
            if a is None:
                continue
            # Continuation: positive funding + rising OI with up move
            ret = (c15[i].close - c15[i - 8].close) / max(c15[i - 8].close, 1e-9)
            if fr > 0.00005 and oi_chg > 0.02 and ret > 0.008:
                out.append(
                    ExecutorSignal(
                        side="Buy",
                        regime="TRENDING_UP",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(c15[i].close - 1.4 * a),
                        target_price=float(c15[i].close + 2.2 * a),
                        stop_basis="price_structure_plus_derivative_context",
                        target_basis="funding_oi_continuation_target",
                        event_id="funding_oi_aligned_long",
                        confirmation="funding_pos_oi_rising_price_up",
                        extras={"funding_rate": fr, "oi_change": oi_chg, "proxy_used": False},
                    )
                )
                last = i
            elif fr < -0.00005 and oi_chg > 0.02 and ret < -0.008:
                out.append(
                    ExecutorSignal(
                        side="Sell",
                        regime="TRENDING_DOWN",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(c15[i].close + 1.4 * a),
                        target_price=float(c15[i].close - 2.2 * a),
                        stop_basis="price_structure_plus_derivative_context",
                        target_basis="funding_oi_continuation_target",
                        event_id="funding_oi_aligned_short",
                        confirmation="funding_neg_oi_rising_price_down",
                        extras={"funding_rate": fr, "oi_change": oi_chg, "proxy_used": False},
                    )
                )
                last = i
        return out


class FundingOiContrarianExecutor(ComponentExecutor):
    component_id = "FUNDING_OI_CONTRARIAN"
    required_capabilities = ("DERIVATIVES_HISTORY_ELIGIBLE", "PRICE_HISTORY_ELIGIBLE")

    def scan(self, ctx: ScanContext, *, stride: int = 20, cooldown: int = 40) -> list[ExecutorSignal]:
        out: list[ExecutorSignal] = []
        if not ctx.funding_points or not ctx.oi_points:
            return out
        c15 = ctx.candles_15
        last = -10_000
        for i in range(40, len(c15) - 8, stride):
            if i - last < cooldown:
                continue
            ts = c15[i].ts_ms
            fr = lookup_series(ctx.funding_points, ts, "funding_rate")
            oi = lookup_series(ctx.oi_points, ts, "open_interest")
            if fr is None or oi is None:
                continue
            a = atr(c15, i)
            if a is None:
                continue
            # Extreme funding fade
            if fr > 0.0002:
                out.append(
                    ExecutorSignal(
                        side="Sell",
                        regime="RANGE",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(c15[i].close + 1.2 * a),
                        target_price=float(c15[i].close - 1.8 * a),
                        stop_basis="crowded_long_invalidation",
                        target_basis="funding_mean_reversion_target",
                        event_id="funding_extreme_fade_short",
                        confirmation="extreme_positive_funding",
                        extras={"funding_rate": fr, "proxy_used": False},
                    )
                )
                last = i
            elif fr < -0.0002:
                out.append(
                    ExecutorSignal(
                        side="Buy",
                        regime="RANGE",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(c15[i].close - 1.2 * a),
                        target_price=float(c15[i].close + 1.8 * a),
                        stop_basis="crowded_short_invalidation",
                        target_basis="funding_mean_reversion_target",
                        event_id="funding_extreme_fade_long",
                        confirmation="extreme_negative_funding",
                        extras={"funding_rate": fr, "proxy_used": False},
                    )
                )
                last = i
        return out


class RegimeTransitionVetoExecutor(ComponentExecutor):
    """Veto component — produces no entries; used as gate by research runner."""

    component_id = "REGIME_TRANSITION_VETO"

    def scan(self, ctx: ScanContext, *, stride: int = 16, cooldown: int = 24) -> list[ExecutorSignal]:
        return []

    def veto(self, ctx: ScanContext, i: int) -> bool:
        c15 = ctx.candles_15
        if i < 30:
            return True
        a = atr(c15, i)
        a_prev = atr(c15, i - 10)
        if a is None or a_prev is None or a_prev <= 0:
            return False
        return (a / a_prev) > 2.5  # chaos expansion veto


class MarkIndexBasisExecutor(ComponentExecutor):
    component_id = "MARK_INDEX_BASIS_ANOMALY"
    required_capabilities = ("DERIVATIVES_HISTORY_ELIGIBLE", "PRICE_HISTORY_ELIGIBLE")

    def scan(self, ctx: ScanContext, *, stride: int = 16, cooldown: int = 30) -> list[ExecutorSignal]:
        out: list[ExecutorSignal] = []
        if not ctx.mark_candles or not ctx.index_candles:
            return out
        c15 = ctx.candles_15
        last = -10_000
        for i in range(40, len(c15) - 8, stride):
            if i - last < cooldown:
                continue
            ts = c15[i].ts_ms
            im = asof_index(ctx.mark_candles, ts)
            ii = asof_index(ctx.index_candles, ts)
            if im is None or ii is None:
                continue
            mark = ctx.mark_candles[im].close
            index = ctx.index_candles[ii].close
            if index <= 0:
                continue
            basis = (mark - index) / index
            a = atr(c15, i)
            if a is None:
                continue
            if basis > 0.0015:
                out.append(
                    ExecutorSignal(
                        side="Sell",
                        regime="RANGE",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(c15[i].close + 1.1 * a),
                        target_price=float(c15[i].close - 1.5 * a),
                        stop_basis="basis_dislocation_invalidation",
                        target_basis="basis_normalization_target",
                        event_id="mark_premium_fade",
                        confirmation="mark_index_basis_elevated",
                        extras={"basis": basis, "proxy_used": False},
                    )
                )
                last = i
            elif basis < -0.0015:
                out.append(
                    ExecutorSignal(
                        side="Buy",
                        regime="RANGE",
                        entry_index=i,
                        entry_price=float(c15[i].close),
                        stop_price=float(c15[i].close - 1.1 * a),
                        target_price=float(c15[i].close + 1.5 * a),
                        stop_basis="basis_dislocation_invalidation",
                        target_basis="basis_normalization_target",
                        event_id="mark_discount_fade",
                        confirmation="mark_index_basis_depressed",
                        extras={"basis": basis, "proxy_used": False},
                    )
                )
                last = i
        return out


class VolumeExpansionExecutor(ComponentExecutor):
    component_id = "VOLUME_EXPANSION_EVENT"

    def scan(self, ctx: ScanContext, *, stride: int = 10, cooldown: int = 26) -> list[ExecutorSignal]:
        out: list[ExecutorSignal] = []
        c15 = ctx.candles_15
        last = -10_000
        for i in range(40, len(c15) - 8, stride):
            if i - last < cooldown:
                continue
            a = atr(c15, i)
            if a is None:
                continue
            vols = [x.volume for x in c15[i - 30 : i]]
            mean_v = sum(vols) / len(vols)
            var = sum((v - mean_v) ** 2 for v in vols) / len(vols)
            std = var**0.5 or 1e-9
            z = (c15[i].volume - mean_v) / std
            if z < 2.5:
                continue
            side = "Buy" if c15[i].close > c15[i - 1].close else "Sell"
            stop = c15[i].close - 1.15 * a if side == "Buy" else c15[i].close + 1.15 * a
            target = c15[i].close + 2.0 * a if side == "Buy" else c15[i].close - 2.0 * a
            out.append(
                ExecutorSignal(
                    side=side,
                    regime="VOL_EXPAND",
                    entry_index=i,
                    entry_price=float(c15[i].close),
                    stop_price=float(stop),
                    target_price=float(target),
                    stop_basis="volume_spike_invalidation",
                    target_basis="volume_expansion_followthrough",
                    event_id="volume_zscore_spike",
                    confirmation=f"volume_z={round(z, 2)}",
                    extras={"volume_z": z},
                )
            )
            last = i
        return out


_REGISTRY: dict[str, ComponentExecutor] = {
    "TREND_CONTINUATION": TrendContinuationExecutor(),
    "STRUCTURAL_RETEST": StructuralRetestExecutor(),
    "BREAKOUT": BreakoutExecutor(),
    "FAILED_BREAKOUT": FailedBreakoutExecutor(),
    "MOMENTUM_ACCELERATION": MomentumAccelerationExecutor(),
    "VOLATILITY_EXPANSION": VolatilityExpansionExecutor(),
    "VWAP_MEAN_REVERSION": VwapMeanReversionExecutor(),
    "STRUCTURAL_MEAN_REVERSION": StructuralMeanReversionExecutor(),
    "RELATIVE_STRENGTH": RelativeStrengthExecutor(),
    "CROSS_SECTIONAL_MOMENTUM": CrossSectionalMomentumExecutor(),
    "LIQUIDITY_SWEEP_REVERSAL": LiquiditySweepExecutor(),
    "FUNDING_OI_CONTINUATION": FundingOiContinuationExecutor(),
    "FUNDING_OI_CONTRARIAN": FundingOiContrarianExecutor(),
    "REGIME_TRANSITION_VETO": RegimeTransitionVetoExecutor(),
    "MARK_INDEX_BASIS_ANOMALY": MarkIndexBasisExecutor(),
    "VOLUME_EXPANSION_EVENT": VolumeExpansionExecutor(),
}


def get_executor(component_id: str) -> ComponentExecutor:
    if component_id not in _REGISTRY:
        return NotImplementedExecutor(component_id)
    return _REGISTRY[component_id]


def executor_registry() -> dict[str, Any]:
    comps = []
    implemented = 0
    for cid in COMPONENT_IDS:
        ex = get_executor(cid)
        implemented += int(ex.implemented)
        comps.append(
            {
                "component_id": cid,
                "implemented": ex.implemented,
                "status": "IMPLEMENTED" if ex.implemented else "NOT_IMPLEMENTED",
                "executor_class": ex.__class__.__name__,
                "executor_checksum": ex.checksum(),
                "required_capabilities": list(ex.required_capabilities),
                "silent_family_fallback": False,
            }
        )
    return {
        "schema": "component_executor_registry_v1_1",
        "registered_component_count": len(COMPONENT_IDS),
        "implemented_component_count": implemented,
        "not_implemented_component_count": len(COMPONENT_IDS) - implemented,
        "components": comps,
        "family_bucket_dispatch_removed": True,
    }
