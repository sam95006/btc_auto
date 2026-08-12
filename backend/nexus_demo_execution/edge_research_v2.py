"""Edge Research V2 — deep H1/H2/H3 research with nested chronological WF.

Offline only. Max 9 pre-registered hypotheses. No new OOS execution.
"""
from __future__ import annotations

import statistics
from collections import Counter
from copy import deepcopy
from typing import Any

from backend.nexus_demo_execution.cohort_edge_research import _summ_rows
from backend.nexus_demo_execution.cohort_matrix import build_context
from backend.nexus_demo_execution.edge_research_v2_hypotheses import HYPOTHESES_V2, TIMEFRAME_JUSTIFICATION
from backend.nexus_demo_execution.historical_market_data import Candle, MarketDataset
from backend.nexus_demo_execution.market_event_sim import MarketCandidate
from backend.nexus_demo_execution.oos_risk_audit import (
    CONSUMED_OOS_ID,
    CONSUMED_STATUS,
    compute_mfe_mae,
    simulate_with_risk_sizing,
)
from backend.nexus_demo_execution.session_limits import (
    MIN_NET_REWARD_RISK_RATIO,
    MIN_NET_REWARD_TO_COST,
    TAKER_FEE_RATE_DEFAULT,
)
from backend.nexus_demo_execution.structural_geometry_qualify import CandidateEvidence

MIN_SAMPLE_REPLAY = 20
MIN_SAMPLE_FOLD = 8
STRONG_NET_PF = 1.15

def audit_datasets(datasets: list[MarketDataset], *, stride: int = 12) -> dict[str, Any]:
    rows = []
    labels: Counter[str] = Counter()
    vol_b: Counter[str] = Counter()
    trend_b: Counter[str] = Counter()
    for ds in datasets:
        days = (ds.end_time - ds.start_time) / 86_400_000.0 if ds.end_time > ds.start_time else 0.0
        rows.append(
            {
                "symbol": ds.symbol,
                "interval": ds.interval,
                "start_time": ds.start_time,
                "end_time": ds.end_time,
                "calendar_days": round(days, 2),
                "record_count": ds.record_count,
                "missing_intervals": ds.missing_interval_count,
                "duplicate_intervals": ds.duplicate_interval_count,
                "checksum": ds.data_checksum,
                "classification": ds.classification,
                "source_endpoint": ds.source_endpoint,
            }
        )
        for i in range(50, len(ds.candles), max(1, stride)):
            ctx = build_context(ds.candles[: i + 1])
            for L in ctx.regime_labels:
                labels[L] += 1
            atr = ctx.atr or 0.0
            last = ctx.last.close
            if last > 0 and atr > 0:
                pct = atr / last
                vol_b["high" if pct > 0.008 else ("low" if pct < 0.003 else "mid")] += 1
            if "TRENDING_UP" in ctx.regime_labels:
                trend_b["bull_trend"] += 1
            elif "TRENDING_DOWN" in ctx.regime_labels:
                trend_b["bear_trend"] += 1
            elif "RANGE" in ctx.regime_labels:
                trend_b["range"] += 1
    total_trend = sum(trend_b.values()) or 1
    has_breakout = labels.get("BREAKOUT", 0) > 50
    has_reversal = labels.get("REVERSAL", 0) > 50
    has_hvol = labels.get("HIGH_VOLATILITY", 0) > 50
    has_bull = trend_b.get("bull_trend", 0) / total_trend >= 0.08
    has_bear = trend_b.get("bear_trend", 0) / total_trend >= 0.08
    has_range = trend_b.get("range", 0) / total_trend >= 0.2
    calendar_days = max((r["calendar_days"] for r in rows), default=0)
    insufficient = calendar_days < 360 or not (has_bull and has_bear and has_range and has_breakout)
    return {
        "datasets": rows,
        "regime_distribution": dict(labels),
        "volatility_distribution": dict(vol_b),
        "trend_direction_distribution": dict(trend_b),
        "funding_event_coverage": "DATA_UNAVAILABLE",
        "includes": {
            "bull_trend": has_bull,
            "bear_trend": has_bear,
            "range": has_range,
            "high_volatility": has_hvol,
            "low_volatility": vol_b.get("low", 0) > 50,
            "breakout": has_breakout,
            "reversal": has_reversal,
            "event_risk_periods": False,
        },
        "DATASET_REGIME_COVERAGE_INSUFFICIENT": insufficient,
        "dataset_regime_coverage_status": (
            "DATASET_REGIME_COVERAGE_INSUFFICIENT" if insufficient else "DATASET_REGIME_COVERAGE_ADEQUATE"
        ),
        "note": "Five trend-following trades are not strategy evidence regardless of PnL.",
    }


def _sma(xs: list[float], n: int) -> float | None:
    if len(xs) < n:
        return None
    return sum(xs[-n:]) / float(n)


def _htf_bearish_series(ds_htf: MarketDataset | None) -> set[int]:
    """Precompute HTF timestamps where SMA20 < SMA50 and price below SMA20."""
    out: set[int] = set()
    if ds_htf is None or len(ds_htf.candles) < 55:
        return out
    closes = [c.close for c in ds_htf.candles]
    for i in range(54, len(ds_htf.candles)):
        s20 = sum(closes[i - 19 : i + 1]) / 20.0
        s50 = sum(closes[i - 49 : i + 1]) / 50.0
        if closes[i] < s20 and s20 <= s50 * 1.002:
            out.add(ds_htf.candles[i].ts_ms)
    return out


def _htf_bearish_at(bearish_ts: set[int], ds_htf: MarketDataset | None, ts_ms: int) -> bool:
    if not bearish_ts or ds_htf is None:
        return False
    # nearest HTF bar at or before ts
    hist = [c.ts_ms for c in ds_htf.candles if c.ts_ms <= ts_ms]
    if not hist:
        return False
    return hist[-1] in bearish_ts


def _cost_proxy_usdt(spread_bps: float = 2.0, slip_bps: float = 2.0) -> float:
    notional = 500.0
    return notional * (2 * TAKER_FEE_RATE_DEFAULT + (spread_bps + slip_bps) / 10000.0)


def _level_key(level: float | None) -> str:
    if level is None:
        return "none"
    return f"{round(level, 4)}"


def hypothesis_triggers(
    hyp: dict[str, Any],
    *,
    hist: list[Candle],
    htf60_bearish: set[int],
    htf240_bearish: set[int],
    htf60: MarketDataset | None,
    htf240: MarketDataset | None,
) -> tuple[bool, str, dict[str, Any]]:
    ctx = build_context(hist)
    last = ctx.last
    atr = ctx.atr or 0.0
    px = last.close
    params = hyp["parameter_values"]
    family = hyp["family"]
    cost = _cost_proxy_usdt()

    if family == "H1":
        if "BREAKOUT" not in ctx.regime_labels:
            return False, "NO_BREAKOUT", {}
        prior = hist[-21:-1]
        if len(prior) < 10:
            return False, "HISTORY_SHORT", {}
        pl = min(c.low for c in prior)
        vol_med = statistics.median([c.volume for c in prior]) or 1.0
        if last.close >= pl:
            return False, "NO_CLOSE_BREAK", {}
        disp = pl - last.close
        min_disp = float(params.get("min_disp_atr", 0.3)) * atr
        if atr > 0 and disp < min_disp:
            return False, "DISPLACEMENT_TOO_SMALL", {}
        move_usdt = (disp / px) * 500.0 if px > 0 else 0.0
        if move_usdt < cost * 1.5:
            return False, "MOVE_BELOW_COST", {}
        max_ext = float(params.get("max_extension_atr", 1.5)) * atr
        if atr > 0 and disp > max_ext:
            return False, "OVEREXTENDED", {}
        if ctx.support and atr > 0 and (last.close - ctx.support) < 0.4 * atr:
            return False, "SUPPORT_BLOCKS_REWARD", {}
        if hyp["variant"] == "A":
            if last.volume < vol_med * float(params.get("vol_mult", 1.2)):
                return False, "VOLUME_WEAK", {}
            return True, "OK", {"level": pl}
        if hyp["variant"] == "B":
            lb = int(params.get("retest_lookback", 8))
            window = hist[-(lb + 1) : -1]
            tagged = any(c.high >= pl for c in window)
            if not (tagged and last.close < pl):
                return False, "NO_FAILED_RETEST", {}
            return True, "OK", {"level": pl}
        if hyp["variant"] == "C":
            if last.volume < vol_med * float(params.get("vol_mult", 1.35)):
                return False, "VOLUME_WEAK", {}
            ranges = [(c.high - c.low) for c in prior]
            med_r = statistics.median(ranges) if ranges else atr
            if atr < med_r * float(params.get("atr_vs_median_min", 1.25)):
                return False, "VOL_NOT_EXPANDED", {}
            return True, "OK", {"level": pl}

    if family == "H2":
        if "RANGE" not in ctx.regime_labels:
            return False, "NOT_RANGE", {}
        if "BREAKOUT" in ctx.regime_labels:
            return False, "BREAKOUT_EXPANSION", {}
        if "TRENDING_UP" in ctx.regime_labels:
            return False, "TRENDING_UP_BLOCK", {}
        vwap = ctx.vwap_proxy or px
        dist = (px - vwap) / px if px > 0 else 0.0
        if dist < float(params.get("min_vwap_dist", 0.0025)):
            return False, "INSUFFICIENT_VWAP_DIST", {}
        if ctx.resistance is None:
            return False, "NO_RESISTANCE", {}
        if abs(px - ctx.resistance) / px > 0.006:
            return False, "NOT_NEAR_UPPER_BOUNDARY", {}
        if atr > 0 and ctx.support is not None:
            width = (ctx.resistance - ctx.support) / atr
            if width < float(params.get("min_range_width_atr", 0.8)):
                return False, "NARROW_RANGE_COST_DOMINATED", {}
        if dist * 500.0 < cost * 1.6:
            return False, "RETURN_DISTANCE_INSUFFICIENT", {}
        if hyp["variant"] == "A":
            if last.close >= last.open:
                return False, "NO_REJECTION", {}
            return True, "OK", {"level": ctx.resistance}
        if hyp["variant"] == "B":
            if last.close >= last.open:
                return False, "NO_MOMENTUM_LOSS", {}
            return True, "OK", {"level": ctx.resistance}
        if hyp["variant"] == "C":
            prior = hist[-15:-1]
            if not prior:
                return False, "HISTORY_SHORT", {}
            med_atr_proxy = statistics.median([(c.high - c.low) for c in prior])
            if atr > med_atr_proxy * float(params.get("atr_contraction_max", 0.9)):
                return False, "ATR_NOT_CONTRACTING", {}
            if last.close >= last.open:
                return False, "NO_REJECTION", {}
            return True, "OK", {"level": ctx.resistance}

    if family == "H3":
        if "TRENDING_DOWN" not in ctx.regime_labels:
            return False, "NOT_TRENDING_DOWN", {}
        look = int(params.get("structure_lookback", 12))
        window = hist[-look:]
        if len(window) < look:
            return False, "HISTORY_SHORT", {}
        mid = look // 2
        hh1 = max(c.high for c in window[:mid])
        hh2 = max(c.high for c in window[mid:])
        ll1 = min(c.low for c in window[:mid])
        ll2 = min(c.low for c in window[mid:])
        if not (hh2 < hh1 and ll2 < ll1):
            return False, "NO_LH_LL", {}
        if atr <= 0 or (atr / px) < 0.0015:
            return False, "EXPECTED_MOVE_TOO_SMALL", {}
        if ctx.support and atr > 0 and (px - ctx.support) < 0.45 * atr:
            return False, "IMMEDIATE_SUPPORT", {}
        if (1.2 * atr / px) * 500.0 < cost * 1.5:
            return False, "MOVE_BELOW_COST", {}
        if hyp["variant"] == "A":
            if last.close >= last.open:
                return False, "MOMENTUM_WEAK", {}
            return True, "OK", {"level": ctx.swing_high}
        if hyp["variant"] == "B":
            if params.get("require_htf60") and not _htf_bearish_at(htf60_bearish, htf60, last.ts_ms):
                return False, "HTF60_NOT_ALIGNED", {}
            if params.get("require_htf240") and not _htf_bearish_at(htf240_bearish, htf240, last.ts_ms):
                return False, "HTF240_NOT_ALIGNED", {}
            return True, "OK", {"level": ctx.swing_high}
        if hyp["variant"] == "C":
            mb = int(params.get("momentum_bars", 8))
            if len(hist) < mb + 2:
                return False, "HISTORY_SHORT", {}
            if hist[-1].close - hist[-mb].close >= 0:
                return False, "MOMENTUM_EXHAUSTED_OR_UP", {}
            if ctx.swing_low and atr > 0:
                if (px - ctx.swing_low) < float(params.get("swing_low_buffer_atr", 0.5)) * atr:
                    return False, "NEAR_SWING_LOW", {}
            return True, "OK", {"level": ctx.swing_high}
    return False, "UNKNOWN", {}


def build_hypothesis_candidates(
    ds15: MarketDataset,
    hyp: dict[str, Any],
    *,
    htf60: MarketDataset | None,
    htf240: MarketDataset | None,
    htf60_bearish: set[int] | None = None,
    htf240_bearish: set[int] | None = None,
    stride: int = 4,
    min_bars: int = 60,
) -> list[MarketCandidate]:
    out: list[MarketCandidate] = []
    cooldown = int(hyp["parameter_values"].get("cooldown_bars", 10))
    last_accept_i = -10_000
    consumed_levels: set[str] = set()
    candles = ds15.candles
    b60 = htf60_bearish if htf60_bearish is not None else _htf_bearish_series(htf60)
    b240 = htf240_bearish if htf240_bearish is not None else _htf_bearish_series(htf240)
    for i in range(min_bars, len(candles) - 2, max(1, stride)):
        if i - last_accept_i < cooldown:
            continue
        # Windowed history for features (no future). Full series not required beyond SMA50/ATR.
        hist = candles[max(0, i - 80) : i + 1]
        ok, _reason, meta = hypothesis_triggers(
            hyp, hist=hist, htf60_bearish=b60, htf240_bearish=b240, htf60=htf60, htf240=htf240
        )
        if not ok:
            continue
        lvl = _level_key(meta.get("level"))
        if lvl in consumed_levels and hyp["family"] in {"H1", "H2"}:
            continue
        last = hist[-1]
        side = "Sell"
        strategy = {"H1": "breakout", "H2": "VWAP_reversion", "H3": "trend_following"}[hyp["family"]]
        regime = {"H1": "BREAKOUT", "H2": "RANGE", "H3": "TRENDING_DOWN"}[hyp["family"]]
        ctx = build_context(hist)
        evidence = CandidateEvidence(
            symbol=ds15.symbol,
            side=side,
            entry_price=float(last.close),
            regime=regime,
            strategy=strategy,
            atr=ctx.atr,
            recent_swing_high=ctx.swing_high,
            recent_swing_low=ctx.swing_low,
            support=ctx.support,
            resistance=ctx.resistance,
            liquidity_levels=[x for x in [ctx.support] if x is not None],
            spread_bps=2.0,
            slippage_bps=2.0,
            fee_rate=TAKER_FEE_RATE_DEFAULT,
            funding_rate=0.0001,
            qty=None,
            data_freshness_sec=0.0,
            ts=float(last.ts_ms),
        )
        out.append(
            MarketCandidate(
                symbol=ds15.symbol,
                side=side,
                strategy=f"{strategy}:{hyp['variant']}",
                regime=regime,
                candidate_snapshot_time=int(last.ts_ms),
                last_input_candle_time=int(last.ts_ms),
                entry_price=float(last.close),
                evidence=evidence,
                future_data_reference_count=0,
                look_ahead_contamination=False,
            )
        )
        last_accept_i = i
        if lvl != "none":
            consumed_levels.add(lvl)
    return out


def _simulate(
    pairs: list[tuple[MarketCandidate, list[Candle]]],
    *,
    apply_costs: bool,
    cost_mode: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cand, sub in pairs:
        c = MarketCandidate(
            symbol=cand.symbol,
            side=cand.side,
            strategy=cand.strategy,
            regime=cand.regime,
            candidate_snapshot_time=cand.candidate_snapshot_time,
            last_input_candle_time=cand.last_input_candle_time,
            entry_price=cand.entry_price,
            evidence=deepcopy(cand.evidence),
            future_data_reference_count=0,
            look_ahead_contamination=False,
        )
        c.evidence.qty = None
        trade, meta = simulate_with_risk_sizing(
            candidate=c, subsequent=sub, cost_mode=cost_mode, apply_costs=apply_costs
        )
        row: dict[str, Any] = {
            "symbol": c.symbol,
            "side": c.side,
            "strategy": c.strategy,
            "regime": c.regime,
            "entry_status": trade.entry_status,
            "exit_status": trade.exit_status,
            "block_reason": getattr(meta, "block_reason", None) if meta else None,
            "gross_pnl": trade.gross_pnl,
            "net_pnl": trade.net_pnl,
            "fees": trade.total_fees,
            "spread_cost": trade.spread_cost,
            "slippage": trade.slippage_cost,
            "funding": trade.funding,
            "entry_price": trade.entry_price,
            "stop": trade.stop,
            "take_profit": trade.take_profit,
            "entry_ts": trade.entry_ts,
            "exit_ts": trade.exit_ts,
            "qty": trade.qty,
        }
        if trade.entry_status == "ENTRY_FILLED" and trade.entry_price is not None:
            fill_i = 0
            for j, bar in enumerate(sub):
                if bar.low <= float(trade.entry_price) <= bar.high:
                    fill_i = j
                    break
            hold: list[Candle] = []
            for bar in sub[fill_i + 1 :]:
                hold.append(bar)
                if trade.exit_ts is not None and bar.ts_ms >= int(trade.exit_ts):
                    break
                if len(hold) >= 48:
                    break
            mfe = compute_mfe_mae(
                side=c.side,
                entry_price=float(trade.entry_price),
                stop=float(trade.stop or 0),
                subsequent_after_fill=hold,
            )
            row.update(mfe)
            row["holding_bars"] = len(hold)
            if trade.stop and trade.entry_price:
                r = abs(float(trade.entry_price) - float(trade.stop)) or 1e-12
                row["reached_1_5R"] = float(mfe.get("mfe") or 0) >= 1.5 * r
            g = abs(float(trade.gross_pnl or 0))
            tot_cost = (
                float(trade.total_fees or 0)
                + float(trade.spread_cost or 0)
                + float(trade.slippage_cost or 0)
                + float(trade.funding or 0)
            )
            row["gross_move_to_total_cost"] = (g / tot_cost) if tot_cost > 1e-12 else None
        rows.append(row)
    return rows


def _failure_v2(rows: list[dict[str, Any]], edge: str) -> str:
    filled = [r for r in rows if r.get("net_pnl") is not None]
    n = len(filled) or 1
    if len(filled) < MIN_SAMPLE_REPLAY:
        return "INSUFFICIENT_SAMPLE"
    if edge == "GROSS_EDGE_DESTROYED_BY_COST":
        return "COST_DOMINATED_CHURN"
    imm = sum(1 for r in filled if r.get("stopped_before_favorable")) / n
    giveback = sum(1 for r in filled if float(r.get("mfe") or 0) > 0 and float(r.get("net_pnl") or 0) < 0) / n
    reach_1r = sum(1 for r in filled if r.get("reached_1R")) / n
    if imm > 0.45:
        return "ENTRY_SELECTION_FAILURE"
    if giveback > 0.45 and reach_1r > 0.3:
        return "EXIT_GIVES_BACK_EDGE"
    if reach_1r < 0.15:
        return "TARGET_UNREACHABLE"
    return "MULTIPLE_FAILURES"


def _edge_from_costs(gross_s: dict[str, Any], base_s: dict[str, Any], adv_s: dict[str, Any]) -> str:
    n = int(base_s.get("completed_trade_count") or 0)
    if n < MIN_SAMPLE_REPLAY:
        return "INSUFFICIENT_SAMPLE"
    g_pf = gross_s.get("gross_profit_factor") or gross_s.get("profit_factor")
    g_exp = gross_s.get("gross_expectancy") or gross_s.get("expectancy")
    if g_pf is None or float(g_pf) <= 1.05 or (g_exp is not None and float(g_exp) <= 0):
        return "NO_GROSS_EDGE"
    b_pf = base_s.get("net_profit_factor") or base_s.get("profit_factor")
    a_pf = adv_s.get("net_profit_factor") or adv_s.get("profit_factor")
    if b_pf is not None and float(b_pf) < 1.0:
        return "GROSS_EDGE_DESTROYED_BY_COST"
    if a_pf is not None and float(a_pf) >= 1.0 and b_pf is not None and float(b_pf) >= 1.0:
        return "EDGE_SURVIVES_ADVERSE_COST"
    if b_pf is not None and float(b_pf) >= 1.0:
        return "EDGE_SURVIVES_BASE_COST"
    return "EDGE_UNSTABLE"


def _promote(status_inputs: dict[str, Any]) -> str:
    base = status_inputs["base"]
    adv = status_inputs["adverse"]
    gross = status_inputs["gross"]
    fold_ok = status_inputs["fold_positive_count"]
    fold_usable = status_inputs["fold_usable_count"]
    symbols = base.get("symbols") or []
    n = int(base.get("completed_trade_count") or 0)
    if n < MIN_SAMPLE_REPLAY:
        return "INSUFFICIENT_SAMPLE"
    g_exp = gross.get("gross_expectancy") or gross.get("expectancy")
    n_exp = base.get("net_expectancy") or base.get("expectancy")
    n_pf = base.get("net_profit_factor") or base.get("profit_factor")
    a_pf = adv.get("net_profit_factor") or adv.get("profit_factor")
    mdd = base.get("maximum_drawdown")
    if not (
        g_exp is not None
        and float(g_exp) > 0
        and n_exp is not None
        and float(n_exp) > 0
        and n_pf is not None
        and float(n_pf) > 1.0
        and len(symbols) >= 2
    ):
        return "REJECTED"
    if (
        fold_usable >= 3
        and fold_ok >= 2
        and float(n_pf) >= STRONG_NET_PF
        and a_pf is not None
        and float(a_pf) >= 0.95
        and (mdd is None or float(mdd) > -40.0)
        and len(symbols) >= 2
    ):
        return "WALK_FORWARD_VALIDATED"
    return "REPLAY_VALIDATED"


def _churn_diagnosis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    filled = [r for r in rows if r.get("net_pnl") is not None]
    if not filled:
        return {"filled": 0}
    holds = [int(r.get("holding_bars") or 0) for r in filled]
    gross_moves = [abs(float(r.get("gross_pnl") or 0)) for r in filled]
    nets = [float(r.get("net_pnl") or 0) for r in filled]
    ratios = [float(r["gross_move_to_total_cost"]) for r in filled if r.get("gross_move_to_total_cost") is not None]
    return {
        "filled": len(filled),
        "entry_fees": round(sum(float(r.get("fees") or 0) for r in filled) / 2.0, 8),
        "exit_fees": round(sum(float(r.get("fees") or 0) for r in filled) / 2.0, 8),
        "spread": round(sum(float(r.get("spread_cost") or 0) for r in filled), 8),
        "slippage": round(sum(float(r.get("slippage") or 0) for r in filled), 8),
        "funding": round(sum(float(r.get("funding") or 0) for r in filled), 8),
        "trade_frequency": len(filled),
        "median_holding_bars": statistics.median(holds) if holds else None,
        "median_gross_move": statistics.median(gross_moves) if gross_moves else None,
        "median_net_move": statistics.median(nets) if nets else None,
        "median_gross_move_to_total_cost": statistics.median(ratios) if ratios else None,
    }


def _mfe_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    filled = [r for r in rows if r.get("net_pnl") is not None]
    n = len(filled) or 1
    return {
        "n": len(filled),
        "pct_0_5R": sum(1 for r in filled if r.get("reached_0_5R")) / n,
        "pct_1R": sum(1 for r in filled if r.get("reached_1R")) / n,
        "pct_1_5R": sum(1 for r in filled if r.get("reached_1_5R")) / n,
        "pct_stopped_before_positive": sum(1 for r in filled if r.get("stopped_before_favorable")) / n,
        "pct_positive_mfe_negative_pnl": sum(
            1 for r in filled if float(r.get("mfe") or 0) > 0 and float(r.get("net_pnl") or 0) < 0
        )
        / n,
        "avg_time_to_mfe": statistics.fmean([float(r.get("time_to_mfe_bars") or 0) for r in filled]) if filled else None,
        "avg_time_to_mae": statistics.fmean([float(r.get("time_to_mae_bars") or 0) for r in filled]) if filled else None,
    }


def run_edge_research_v2(
    *,
    datasets_15: list[MarketDataset],
    datasets_60: list[MarketDataset],
    datasets_240: list[MarketDataset],
    existing_audit: dict[str, Any],
    consumed_fraction: float = 0.15,
) -> dict[str, Any]:
    assert MIN_NET_REWARD_RISK_RATIO == 1.2
    assert MIN_NET_REWARD_TO_COST == 1.5
    assert all(h["created_before_evaluation"] for h in HYPOTHESES_V2)

    by60 = {d.symbol: d for d in datasets_60}
    by240 = {d.symbol: d for d in datasets_240}
    bear60 = {sym: _htf_bearish_series(ds) for sym, ds in by60.items()}
    bear240 = {sym: _htf_bearish_series(ds) for sym, ds in by240.items()}

    hyp_pairs: dict[str, list[tuple[MarketCandidate, list[Candle]]]] = {}
    for hyp in HYPOTHESES_V2:
        print(f"building {hyp['hypothesis_id']} ...", flush=True)
        pairs: list[tuple[MarketCandidate, list[Candle]]] = []
        for ds in datasets_15:
            cands = build_hypothesis_candidates(
                ds,
                hyp,
                htf60=by60.get(ds.symbol),
                htf240=by240.get(ds.symbol),
                htf60_bearish=bear60.get(ds.symbol),
                htf240_bearish=bear240.get(ds.symbol),
                stride=16,
            )
            by_ts = {c.ts_ms: i for i, c in enumerate(ds.candles)}
            for cand in cands:
                idx = by_ts.get(cand.candidate_snapshot_time)
                if idx is None:
                    continue
                pairs.append((cand, ds.candles[idx + 1 :]))
        pairs.sort(key=lambda x: x[0].candidate_snapshot_time)
        cut = int(len(pairs) * (1.0 - consumed_fraction))
        hyp_pairs[hyp["hypothesis_id"]] = pairs[:cut]
        print(f"built {hyp['hypothesis_id']} research_pairs={cut}", flush=True)

    results: list[dict[str, Any]] = []
    for hyp in HYPOTHESES_V2:
        pairs = hyp_pairs[hyp["hypothesis_id"]]
        print(
            f"sim {hyp['hypothesis_id']} pairs={len(pairs)}",
            flush=True,
        )
        m = len(pairs)
        cuts = [0, m // 3, 2 * m // 3, m]
        fold_summaries = []
        fold_positive = 0
        fold_usable = 0
        base_rows = _simulate(pairs, apply_costs=True, cost_mode="BASE_CONSERVATIVE")
        base_s = _summ_rows(base_rows)
        # Cost A/D only when there is enough structure to interpret; still run gross for edge class.
        gross_rows = _simulate(pairs, apply_costs=False, cost_mode="GROSS_NO_COST_DIAGNOSTIC")
        gross_s = _summ_rows(gross_rows)
        if int(base_s.get("completed_trade_count") or 0) >= MIN_SAMPLE_FOLD:
            adv_rows = _simulate(pairs, apply_costs=True, cost_mode="ADVERSE_COST_STRESS")
            adv_s = _summ_rows(adv_rows)
        else:
            adv_s = dict(base_s)

        for fi in range(3):
            a, b = cuts[fi], cuts[fi + 1]
            frows = base_rows[a:b]
            fs = _summ_rows(frows)
            fold_summaries.append(
                {
                    "fold": f"outer_{fi + 1}",
                    "pair_count": b - a,
                    "summary": fs,
                    "entry_triggered_count": sum(
                        1
                        for r in frows
                        if r.get("entry_status") in {"ENTRY_FILLED", "ENTRY_TRIGGERED_NOT_FILLED"}
                    ),
                }
            )
            cn = int(fs.get("completed_trade_count") or 0)
            if cn >= MIN_SAMPLE_FOLD:
                fold_usable += 1
                pf = fs.get("net_profit_factor") or fs.get("profit_factor")
                exp = fs.get("net_expectancy") or fs.get("expectancy")
                if pf is not None and float(pf) > 1 and exp is not None and float(exp) > 0:
                    fold_positive += 1

        edge = _edge_from_costs(gross_s, base_s, adv_s)
        failure = _failure_v2(base_rows, edge)
        replay = {
            **base_s,
            "gross_pnl": gross_s.get("gross_pnl"),
            "gross_profit_factor": gross_s.get("gross_profit_factor") or gross_s.get("profit_factor"),
            "gross_expectancy": gross_s.get("gross_expectancy") or gross_s.get("expectancy"),
        }
        status = _promote(
            {
                "base": replay,
                "adverse": adv_s,
                "gross": gross_s,
                "fold_positive_count": fold_positive,
                "fold_usable_count": fold_usable,
            }
        )
        results.append(
            {
                "hypothesis_id": hyp["hypothesis_id"],
                "family": hyp["family"],
                "variant": hyp["variant"],
                "cohort": hyp["cohort"],
                "status": status,
                "edge_classification": edge,
                "failure_classification": failure,
                "created_before_evaluation": True,
                "replay": replay,
                "cost_versions": {
                    "GROSS_NO_COST_DIAGNOSTIC": gross_s,
                    "BASE_CONSERVATIVE_COST": base_s,
                    "OBSERVED_COST": base_s,
                    "ADVERSE_COST_STRESS": adv_s,
                },
                "folds": fold_summaries,
                "churn_diagnosis": _churn_diagnosis(base_rows),
                "mfe_mae": _mfe_report(base_rows),
                "consumed_oos_used": False,
            }
        )

    family_best: dict[str, str] = {}
    for fam in ("H1", "H2", "H3"):
        cands = [r for r in results if r["family"] == fam]
        # Inner selection among pre-registered variants only: prefer sample, then fold1-2 net exp.
        scored = []
        for r in cands:
            n = int((r.get("replay") or {}).get("completed_trade_count") or 0)
            f12 = []
            for fr in r["folds"][:2]:
                s = fr.get("summary") or {}
                if s.get("net_expectancy") is not None:
                    f12.append(float(s["net_expectancy"]))
            score = statistics.fmean(f12) if f12 else -999.0
            scored.append((n, score, r["hypothesis_id"]))
        scored.sort(reverse=True)
        family_best[fam] = scored[0][2] if scored else ""

    def _fam_metric(fam: str) -> dict[str, Any]:
        best_id = family_best.get(fam)
        r = next((x for x in results if x["hypothesis_id"] == best_id), None)
        if r is None:
            return {"status": "INSUFFICIENT_SAMPLE", "trades": 0}
        rep = r["replay"]
        adv = r["cost_versions"]["ADVERSE_COST_STRESS"]
        return {
            "status": r["status"],
            "hypothesis_id": r["hypothesis_id"],
            "trades": rep.get("completed_trade_count"),
            "gross_expectancy": rep.get("gross_expectancy"),
            "net_expectancy": rep.get("net_expectancy"),
            "base_pf": rep.get("net_profit_factor") or rep.get("profit_factor"),
            "adverse_pf": adv.get("net_profit_factor") or adv.get("profit_factor"),
            "mdd": rep.get("maximum_drawdown"),
            "edge": r["edge_classification"],
            "failure": r["failure_classification"],
            "mfe_mae": r.get("mfe_mae"),
            "churn_diagnosis": r.get("churn_diagnosis"),
        }

    statuses = [r["status"] for r in results]
    wf_any = any(s == "WALK_FORWARD_VALIDATED" for s in statuses)
    end_ms = max((d.end_time for d in datasets_15), default=0)
    oos_reservation = {
        "reserved_start": end_ms + 1,
        "reserved_end": end_ms + 45 * 86_400_000,
        "symbols": sorted({d.symbol for d in datasets_15}),
        "intervals": ["15", "60", "240"],
        "created_before_download": True,
        "downloaded": False,
        "executed": False,
        "status": "NEW_UNTOUCHED_OOS_PLAN_READY" if wf_any else "NEW_UNTOUCHED_OOS_PLAN_DEFERRED",
    }
    fails = Counter(r["failure_classification"] for r in results)
    primary_fail = fails.most_common(1)[0][0] if fails else "MULTIPLE_FAILURES"
    if wf_any:
        recommendation = "NEXUS_NEW_OOS_PLAN_READY"
    elif any(s == "REPLAY_VALIDATED" for s in statuses):
        recommendation = "NEXUS_NEW_WALK_FORWARD_READY"
    else:
        recommendation = "NEXUS_STRATEGY_EDGE_RESEARCH_REQUIRED"

    expanded_meta = {
        "symbols": sorted({d.symbol for d in datasets_15}),
        "intervals": sorted({d.interval for d in datasets_15 + datasets_60 + datasets_240}),
        "start": min((d.start_time for d in datasets_15), default=0),
        "end": max((d.end_time for d in datasets_15), default=0),
        "record_count": sum(d.record_count for d in datasets_15 + datasets_60 + datasets_240),
        "checksums": {
            f"{d.symbol}_{d.interval}": d.data_checksum for d in datasets_15 + datasets_60 + datasets_240
        },
    }
    return {
        "hypotheses_registered": HYPOTHESES_V2,
        "hypotheses_executed": [h["hypothesis_id"] for h in HYPOTHESES_V2],
        "hypotheses_registered_count": len(HYPOTHESES_V2),
        "timeframe_justification": TIMEFRAME_JUSTIFICATION,
        "existing_dataset_audit": existing_audit,
        "expanded_market_data": expanded_meta,
        "family_best_by_inner_selection": family_best,
        "hypothesis_results": results,
        "breakout_sell": _fam_metric("H1"),
        "vwap_range_sell": _fam_metric("H2"),
        "trend_down_sell": _fam_metric("H3"),
        "cohorts_replay_validated": sum(1 for s in statuses if s == "REPLAY_VALIDATED"),
        "cohorts_walk_forward_validated": sum(1 for s in statuses if s == "WALK_FORWARD_VALIDATED"),
        "cohorts_rejected": sum(1 for s in statuses if s == "REJECTED"),
        "cohorts_insufficient_sample": sum(1 for s in statuses if s == "INSUFFICIENT_SAMPLE"),
        "primary_remaining_failure": primary_fail,
        "oi_funding_cvd_data_plan": {
            "ready": True,
            "status": "READ_ONLY_PLAN_ONLY",
            "endpoints": {
                "open_interest": {"path": "/v5/market/open-interest", "status": "API_UNSUPPORTED_IN_THIS_TASK"},
                "funding": {"path": "/v5/market/funding/history", "status": "API_UNSUPPORTED_IN_THIS_TASK"},
                "cvd_trades": {"path": "/v5/market/recent-trade", "status": "INSUFFICIENT_HISTORY_FOR_CVD"},
            },
            "rules": ["No fake zero", "DATA_UNAVAILABLE when raw missing", "Do not promote cohorts"],
            "promote_in_this_task": False,
        },
        "oi_funding_cvd_data_plan_ready": True,
        "new_untouched_oos_plan": oos_reservation,
        "new_untouched_oos_plan_ready": bool(wf_any),
        "oos_cohort_status": CONSUMED_STATUS,
        "consumed_oos_id": CONSUMED_OOS_ID,
        "floors_unchanged": True,
        "wallet_delta_classification": "UNKNOWN",
        "wallet_delta_unattributed": -0.97052039,
        "risk_review_packet_ready": False,
        "shadow_status": "NOT_APPLIED",
        "qualification_complete": False,
        "safety": {
            "EXCHANGE_WRITE": False,
            "DEMO_AUTONOMOUS_ENABLED": False,
            "MAINNET": False,
            "REAL_MONEY": False,
            "24H_GATE_APPROVED": False,
        },
        "recommendation": recommendation,
    }
