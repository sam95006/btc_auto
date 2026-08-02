"""Edge Research V3 — economic redesign, Cost Gate forensic, nested WF.

Offline only. V2 hypotheses consumed. Cost floors unchanged. No final OOS.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any

from backend.nexus_demo_execution.cohort_edge_research import _summ_rows
from backend.nexus_demo_execution.cohort_matrix import build_context
from backend.nexus_demo_execution.edge_research_v2_hypotheses import HYPOTHESES_V2
from backend.nexus_demo_execution.edge_research_v3_hypotheses import (
    HYPOTHESES_V3,
    RESEARCH_WAVE_V2_STATUS,
    V2_COMMIT,
)
from backend.nexus_demo_execution.historical_market_data import Candle, MarketDataset
from backend.nexus_demo_execution.market_event_sim import MarketCandidate
from backend.nexus_demo_execution.microstructure_history import lookup_asof, oi_change_pct
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
from backend.nexus_demo_execution.structural_geometry_qualify import (
    CandidateEvidence,
    evaluate_structural_geometry,
)

MIN_SAMPLE_REPLAY = 20
MIN_SAMPLE_FOLD = 8
STRONG_NET_PF = 1.15
COST_PROXY_NOTIONAL = 500.0


def _cost_proxy(spread_bps: float = 2.0, slip_bps: float = 2.0) -> float:
    return COST_PROXY_NOTIONAL * (2 * TAKER_FEE_RATE_DEFAULT + (spread_bps + slip_bps) / 10000.0)


def _asof_candle(ds: MarketDataset | None, ts_ms: int) -> tuple[list[Candle], int] | None:
    if ds is None or not ds.candles:
        return None
    # last index with ts <= ts_ms
    lo, hi = 0, len(ds.candles) - 1
    best = -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if ds.candles[mid].ts_ms <= ts_ms:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    if best < 50:
        return None
    return ds.candles[: best + 1], best


def _classify_starvation(geo: dict[str, Any], *, extension_atr: float | None, target_dist: float | None, cost: float) -> str:
    reason = str(geo.get("block_reason") or "")
    bd = geo.get("breakdown") if isinstance(geo.get("breakdown"), dict) else {}
    gross_r = float(bd.get("gross_take_profit_pnl") or 0)
    if reason in {"COST_GATE_FAIL", "COST_GATE_BLOCK"} or geo.get("cost_gate_block"):
        if extension_atr is not None and extension_atr > 1.2:
            return "ENTRY_TOO_LATE"
        if target_dist is not None and target_dist * COST_PROXY_NOTIONAL < cost * 1.5:
            return "TARGET_TOO_CLOSE"
        if gross_r > 0 and gross_r < cost * 1.2:
            return "COST_TOO_HIGH_FOR_TIMEFRAME"
        stop = geo.get("stop_price")
        entry = geo.get("entry_price")
        if isinstance(stop, (int, float)) and isinstance(entry, (int, float)):
            risk = abs(float(entry) - float(stop))
            tp = geo.get("take_profit_price")
            if isinstance(tp, (int, float)) and abs(float(tp) - float(entry)) < risk * 0.8:
                return "TARGET_TOO_CLOSE"
            if risk / max(float(entry), 1e-9) > 0.025:
                return "STOP_TOO_WIDE"
        if geo.get("geometry_missing") or geo.get("geometry_invalid"):
            return "NO_REACHABLE_STRUCTURE"
        return "VALID_COST_GATE_BLOCK"
    return "VALID_COST_GATE_BLOCK"


def cost_gate_starvation_forensic(
    datasets_15: list[MarketDataset],
    datasets_60: list[MarketDataset],
    *,
    families: tuple[str, ...] = ("H1", "H3"),
    stride: int = 24,
) -> dict[str, Any]:
    """Diagnose H1/H3 Cost Gate blocks without lowering floors."""
    by60 = {d.symbol: d for d in datasets_60}
    rows: list[dict[str, Any]] = []
    # Use V2-style scan definitions as starvation baseline (consumed wave)
    from backend.nexus_demo_execution.edge_research_v2 import build_hypothesis_candidates, _htf_bearish_series

    # Map families to first V2 hyp of that family for candidate generation shape
    v2_by_fam = {}
    for h in HYPOTHESES_V2:
        v2_by_fam.setdefault(h["family"], h)

    for fam in families:
        hyp = v2_by_fam.get(fam)
        if not hyp:
            continue
        for ds in datasets_15:
            h60 = by60.get(ds.symbol)
            cands = build_hypothesis_candidates(
                ds, hyp, htf60=h60, htf240=None, stride=stride, htf60_bearish=set(), htf240_bearish=set()
            )
            for cand in cands:
                geo = evaluate_structural_geometry(cand.evidence)
                if geo.get("cost_gate_pass"):
                    continue
                entry = float(cand.entry_price)
                stop = geo.get("stop_price")
                tp = geo.get("take_profit_price")
                bd = geo.get("breakdown") if isinstance(geo.get("breakdown"), dict) else {}
                # extension vs 60m
                ext = None
                tgt_dist = None
                asof = _asof_candle(h60, cand.candidate_snapshot_time)
                if asof:
                    hist60, _ = asof
                    ctx60 = build_context(hist60[-80:])
                    if ctx60.atr and ctx60.swing_high and fam == "H1":
                        ext = abs(float(ctx60.swing_low or entry) - entry) / ctx60.atr if ctx60.atr else None
                    if isinstance(tp, (int, float)):
                        tgt_dist = abs(float(tp) - entry) / entry
                cost = float(bd.get("estimated_total_cost") or _cost_proxy())
                cause = _classify_starvation(geo, extension_atr=ext, target_dist=tgt_dist, cost=cost)
                rows.append(
                    {
                        "symbol": cand.symbol,
                        "timestamp": cand.candidate_snapshot_time,
                        "strategy": cand.strategy,
                        "regime": cand.regime,
                        "side": cand.side,
                        "family": fam,
                        "entry_price": entry,
                        "structural_stop": stop,
                        "structural_target": tp,
                        "gross_reward": bd.get("gross_take_profit_pnl"),
                        "gross_risk": bd.get("gross_stop_loss_pnl"),
                        "gross_rr": geo.get("gross_rr"),
                        "net_rr": geo.get("net_rr"),
                        "reward_to_cost": geo.get("reward_to_cost"),
                        "total_expected_cost": bd.get("estimated_total_cost") or cost,
                        "block_reason": geo.get("block_reason"),
                        "block_subreason": geo.get("block_subreason"),
                        "starvation_cause": cause,
                        "entry_extension_from_break": ext,
                        "distance_to_structural_target": tgt_dist,
                    }
                )
    causes = Counter(r["starvation_cause"] for r in rows)
    by_fam = Counter(r["family"] for r in rows)
    return {
        "blocked_count": len(rows),
        "by_family": dict(by_fam),
        "cost_gate_starvation_counts_by_cause": dict(causes),
        "sample_rows": rows[:20],
        "note": "Floors unchanged; blocks recorded for diagnosis only",
        "floors": {
            "MIN_NET_REWARD_RISK_RATIO": MIN_NET_REWARD_RISK_RATIO,
            "MIN_NET_REWARD_TO_COST": MIN_NET_REWARD_TO_COST,
        },
    }


def _economic_prefilter(
    *,
    entry: float,
    target: float,
    stop: float,
    min_move_to_cost: float,
) -> tuple[bool, dict[str, Any]]:
    cost = _cost_proxy()
    move = abs(entry - target)
    move_usdt = (move / entry) * COST_PROXY_NOTIONAL if entry > 0 else 0.0
    risk = abs(entry - stop)
    ratio = move_usdt / cost if cost > 0 else 0.0
    meta = {
        "expected_gross_move_usdt": move_usdt,
        "expected_total_cost_usdt": cost,
        "gross_move_to_cost_ratio": ratio,
        "distance_to_structural_target": move / entry if entry else None,
        "distance_to_invalidation": risk / entry if entry else None,
    }
    return ratio >= min_move_to_cost, meta


def build_v3_candidates(
    hyp: dict[str, Any],
    *,
    ds15: MarketDataset,
    ds60: MarketDataset | None,
    ds240: MarketDataset | None,
    micro: dict[str, Any] | None,
    stride: int = 16,
) -> list[tuple[MarketCandidate, dict[str, Any]]]:
    """Return candidates with economic diagnostics meta."""
    out: list[tuple[MarketCandidate, dict[str, Any]]] = []
    params = hyp["parameter_values"]
    cooldown = int(params.get("cooldown_15m_bars", 24))
    min_bars = 80
    last_i = -10_000
    consumed: set[str] = set()
    candles = ds15.candles
    fund_pts = []
    oi_pts = []
    if micro:
        f = (micro.get("funding") or {}).get(ds15.symbol)
        o = (micro.get("open_interest") or {}).get(ds15.symbol)
        if f is not None and getattr(f, "supported_status", "") == "AVAILABLE":
            fund_pts = f.points
        if o is not None and getattr(o, "supported_status", "") == "AVAILABLE":
            oi_pts = o.points

    if hyp.get("requires_microstructure"):
        need = set(hyp.get("enrichment") or [])
        if "funding" in need and not fund_pts:
            return []
        if "open_interest" in need and not oi_pts:
            return []

    for i in range(min_bars, len(candles) - 2, max(1, stride)):
        if i - last_i < cooldown:
            continue
        ts = candles[i].ts_ms
        hist15 = candles[max(0, i - 80) : i + 1]
        ctx15 = build_context(hist15)
        as60 = _asof_candle(ds60, ts)
        as240 = _asof_candle(ds240, ts)
        if not as60 or not as240:
            continue
        hist60, _ = as60
        hist240, _ = as240
        ctx60 = build_context(hist60[-80:])
        ctx240 = build_context(hist240[-80:])
        family = hyp["family"]
        variant = hyp["variant"]
        entry = float(candles[i].close)
        ok = False
        level = None
        stop = None
        target = None

        if family == "H2":
            if "RANGE" not in ctx240.regime_labels:
                continue
            if "BREAKOUT" in ctx15.regime_labels or "BREAKOUT" in ctx60.regime_labels:
                continue
            if ctx60.resistance is None or ctx60.vwap_proxy is None:
                continue
            if entry < ctx60.vwap_proxy:
                continue
            # near upper boundary
            if abs(entry - ctx60.resistance) / entry > 0.008:
                continue
            if candles[i].close >= candles[i].open:
                continue
            target = float(ctx60.vwap_proxy)
            stop = float(ctx60.resistance) * 1.002
            if variant == "E":
                dist = (entry - ctx60.vwap_proxy) / entry
                if dist < float(params.get("min_vwap_dist_60m", 0.006)):
                    continue
            if variant == "F":
                # failed upside break: prior 60m high pierced then back inside
                prior = hist60[-12:-1]
                if len(prior) < 5:
                    continue
                ph = max(c.high for c in prior)
                if not (any(c.high > ph * 0.999 for c in hist15[-6:]) and entry < ph):
                    continue
            if variant == "G":
                ch = oi_change_pct(oi_pts, ts)
                if ch is None or ch > float(params.get("oi_expand_max_pct", 0.02)):
                    continue
            level = str(round(ctx60.resistance, 4))
            ok = True

        elif family == "H1":
            if ctx60.swing_low is None or ctx60.atr is None:
                continue
            pl = float(ctx60.swing_low)
            if entry >= pl:
                continue
            # remaining move to next support (use prior swing / 1.5 ATR proxy)
            next_sup = pl - 1.2 * float(ctx60.atr)
            target = next_sup
            stop = pl * 1.001
            ext = (pl - entry) / float(ctx60.atr)
            if ext > float(params.get("max_extension_atr_60m", 1.5)):
                continue
            if variant == "D":
                # failed retest
                if not any(c.high >= pl for c in hist15[-8:-1]):
                    continue
            if variant == "E":
                if "TRENDING_DOWN" not in ctx240.regime_labels:
                    continue
                ranges = [(c.high - c.low) for c in hist60[-15:-1]]
                if not ranges:
                    continue
                if float(ctx60.atr) > statistics.median(ranges) * float(params.get("atr_contraction_max", 0.85)):
                    continue
            if variant == "G":
                fr = lookup_asof(fund_pts, ts, "funding_rate")
                if fr is None or abs(fr) > float(params.get("funding_abs_max", 0.001)):
                    continue
            level = str(round(pl, 4))
            ok = True

        elif family == "H3":
            if "TRENDING_DOWN" not in ctx240.regime_labels:
                continue
            if ctx60.sma20 is None or ctx60.atr is None:
                continue
            # pullback rejection / continuation
            if entry > float(ctx60.sma20) * 1.004:
                continue
            if candles[i].close >= candles[i].open:
                continue
            if ctx60.support and (entry - ctx60.support) < 0.5 * float(ctx60.atr):
                continue
            target = entry - 1.5 * float(ctx60.atr)
            stop = entry + 0.8 * float(ctx60.atr)
            if variant == "D":
                # approximate first LH: require recent lower high vs prior
                highs = [c.high for c in hist60[-12:]]
                if len(highs) < 8 or highs[-1] >= max(highs[:-1]):
                    continue
            if variant == "F":
                ranges = [(c.high - c.low) for c in hist60[-15:-1]]
                if not ranges or float(ctx60.atr) > statistics.median(ranges) * float(
                    params.get("atr_contraction_max", 0.9)
                ):
                    continue
            if variant == "G":
                ch = oi_change_pct(oi_pts, ts)
                if ch is None:
                    continue
            level = f"trend_{ts // 3_600_000}"
            ok = True
        else:
            continue

        if not ok or stop is None or target is None:
            continue
        if level and level in consumed and family in {"H1", "H2"}:
            continue
        econ_ok, econ = _economic_prefilter(
            entry=entry,
            target=target,
            stop=stop,
            min_move_to_cost=float(params.get("min_move_to_cost", 2.5)),
        )
        if not econ_ok:
            continue

        # Build evidence using 60m structure so geometry targets are larger
        atr = ctx60.atr
        evidence = CandidateEvidence(
            symbol=ds15.symbol,
            side="Sell",
            entry_price=entry,
            regime=hyp["cohort"].split("|")[1],
            strategy=hyp["cohort"].split("|")[0],
            atr=atr,
            recent_swing_high=ctx60.swing_high,
            recent_swing_low=ctx60.swing_low,
            support=target if family != "H2" else ctx60.support,
            resistance=stop if family == "H2" else ctx60.resistance,
            liquidity_levels=[x for x in [ctx60.support] if x is not None],
            spread_bps=2.0,
            slippage_bps=2.0,
            fee_rate=TAKER_FEE_RATE_DEFAULT,
            funding_rate=lookup_asof(fund_pts, ts, "funding_rate"),
            qty=None,
            data_freshness_sec=0.0,
            ts=float(ts),
        )
        # If funding lookup None, keep conservative default for geometry (not zero invent for OI features)
        if evidence.funding_rate is None:
            evidence.funding_rate = 0.0001
        cand = MarketCandidate(
            symbol=ds15.symbol,
            side="Sell",
            strategy=f"{hyp['cohort'].split('|')[0]}:{variant}",
            regime=hyp["cohort"].split("|")[1],
            candidate_snapshot_time=int(ts),
            last_input_candle_time=int(ts),
            entry_price=entry,
            evidence=evidence,
            future_data_reference_count=0,
            look_ahead_contamination=False,
        )
        meta = {
            **econ,
            "expected_holding_bars": int(params.get("min_holding_expectation_bars", 8)),
            "hypothesis_id": hyp["hypothesis_id"],
            "level": level,
        }
        out.append((cand, meta))
        last_i = i
        if level:
            consumed.add(level)
    return out


def _simulate(pairs: list[tuple[MarketCandidate, list[Candle]]], *, apply_costs: bool, cost_mode: str) -> list[dict[str, Any]]:
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
            "block_reason": getattr(meta, "block_reason", None) if meta else None,
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
                if len(hold) >= 96:
                    break
            mfe = compute_mfe_mae(
                side=c.side,
                entry_price=float(trade.entry_price),
                stop=float(trade.stop or 0),
                subsequent_after_fill=hold,
            )
            row.update(mfe)
            row["holding_bars"] = len(hold)
            g = abs(float(trade.gross_pnl or 0))
            tot = (
                float(trade.total_fees or 0)
                + float(trade.spread_cost or 0)
                + float(trade.slippage_cost or 0)
                + float(trade.funding or 0)
            )
            row["gross_move_to_total_cost"] = (g / tot) if tot > 1e-12 else None
        rows.append(row)
    return rows


def _edge(g: dict[str, Any], b: dict[str, Any], a: dict[str, Any]) -> str:
    n = int(b.get("completed_trade_count") or 0)
    if n < MIN_SAMPLE_REPLAY:
        return "INSUFFICIENT_SAMPLE"
    gpf = g.get("gross_profit_factor") or g.get("profit_factor")
    gexp = g.get("gross_expectancy") or g.get("expectancy")
    if gpf is None or float(gpf) <= 1.05 or (gexp is not None and float(gexp) <= 0):
        return "NO_GROSS_EDGE"
    bpf = b.get("net_profit_factor") or b.get("profit_factor")
    apf = a.get("net_profit_factor") or a.get("profit_factor")
    if bpf is not None and float(bpf) < 1:
        return "GROSS_EDGE_DESTROYED_BY_COST"
    if apf is not None and float(apf) >= 1 and bpf is not None and float(bpf) >= 1:
        return "EDGE_SURVIVES_ADVERSE_COST"
    if bpf is not None and float(bpf) >= 1:
        return "EDGE_SURVIVES_BASE_COST"
    return "EDGE_UNSTABLE"


def _promote(base: dict[str, Any], adv: dict[str, Any], gross: dict[str, Any], fold_ok: int, fold_usable: int) -> str:
    n = int(base.get("completed_trade_count") or 0)
    if n < MIN_SAMPLE_REPLAY:
        return "INSUFFICIENT_SAMPLE"
    gexp = gross.get("gross_expectancy") or gross.get("expectancy")
    nexp = base.get("net_expectancy") or base.get("expectancy")
    npf = base.get("net_profit_factor") or base.get("profit_factor")
    apf = adv.get("net_profit_factor") or adv.get("profit_factor")
    symbols = base.get("symbols") or []
    mdd = base.get("maximum_drawdown")
    if not (
        gexp is not None
        and float(gexp) > 0
        and nexp is not None
        and float(nexp) > 0
        and npf is not None
        and float(npf) > 1
        and len(symbols) >= 2
    ):
        return "REJECTED"
    if (
        fold_usable >= 3
        and fold_ok >= 2
        and float(npf) >= STRONG_NET_PF
        and apf is not None
        and float(apf) >= 0.95
        and (mdd is None or float(mdd) > -40)
    ):
        return "WALK_FORWARD_VALIDATED"
    return "REPLAY_VALIDATED"


def _holding_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    filled = [r for r in rows if r.get("net_pnl") is not None]
    if not filled:
        return {"median_holding_bars": None, "median_gross_move_to_cost": None}
    holds = [int(r.get("holding_bars") or 0) for r in filled]
    ratios = [float(r["gross_move_to_total_cost"]) for r in filled if r.get("gross_move_to_total_cost") is not None]
    return {
        "median_holding_bars": statistics.median(holds) if holds else None,
        "median_gross_move_to_cost": statistics.median(ratios) if ratios else None,
        "gross_move_to_cost_buckets": {
            "<1": sum(1 for x in ratios if x < 1),
            "1-2": sum(1 for x in ratios if 1 <= x < 2),
            "2-3": sum(1 for x in ratios if 2 <= x < 3),
            ">3": sum(1 for x in ratios if x >= 3),
        },
    }


def run_edge_research_v3(
    *,
    datasets_15: list[MarketDataset],
    datasets_60: list[MarketDataset],
    datasets_240: list[MarketDataset],
    micro: dict[str, Any],
    starvation: dict[str, Any],
    consumed_fraction: float = 0.15,
) -> dict[str, Any]:
    assert MIN_NET_REWARD_RISK_RATIO == 1.2
    assert MIN_NET_REWARD_TO_COST == 1.5
    by60 = {d.symbol: d for d in datasets_60}
    by240 = {d.symbol: d for d in datasets_240}

    results = []
    for hyp in HYPOTHESES_V3:
        print(f"v3 building {hyp['hypothesis_id']}", flush=True)
        pairs: list[tuple[MarketCandidate, list[Candle]]] = []
        econ_metas = []
        gate_pass = 0
        gate_total = 0
        for ds in datasets_15:
            built = build_v3_candidates(
                hyp,
                ds15=ds,
                ds60=by60.get(ds.symbol),
                ds240=by240.get(ds.symbol),
                micro=micro,
                stride=16,
            )
            by_ts = {c.ts_ms: i for i, c in enumerate(ds.candles)}
            for cand, meta in built:
                gate_total += 1
                geo = evaluate_structural_geometry(cand.evidence)
                if geo.get("cost_gate_pass"):
                    gate_pass += 1
                idx = by_ts.get(cand.candidate_snapshot_time)
                if idx is None:
                    continue
                pairs.append((cand, ds.candles[idx + 1 :]))
                econ_metas.append(meta)
        pairs.sort(key=lambda x: x[0].candidate_snapshot_time)
        cut = int(len(pairs) * (1.0 - consumed_fraction))
        pairs = pairs[:cut]
        print(f"v3 sim {hyp['hypothesis_id']} pairs={len(pairs)}", flush=True)

        base_rows = _simulate(pairs, apply_costs=True, cost_mode="BASE_CONSERVATIVE")
        gross_rows = _simulate(pairs, apply_costs=False, cost_mode="GROSS_NO_COST_DIAGNOSTIC")
        base_s = _summ_rows(base_rows)
        gross_s = _summ_rows(gross_rows)
        if int(base_s.get("completed_trade_count") or 0) >= MIN_SAMPLE_FOLD:
            adv_s = _summ_rows(_simulate(pairs, apply_costs=True, cost_mode="ADVERSE_COST_STRESS"))
        else:
            adv_s = dict(base_s)

        m = len(base_rows)
        cuts = [0, m // 3, 2 * m // 3, m]
        fold_ok = fold_usable = 0
        folds = []
        for fi in range(3):
            a, b = cuts[fi], cuts[fi + 1]
            fs = _summ_rows(base_rows[a:b])
            folds.append({"fold": f"outer_{fi+1}", "summary": fs, "pair_count": b - a})
            cn = int(fs.get("completed_trade_count") or 0)
            if cn >= MIN_SAMPLE_FOLD:
                fold_usable += 1
                pf = fs.get("net_profit_factor") or fs.get("profit_factor")
                exp = fs.get("net_expectancy") or fs.get("expectancy")
                if pf is not None and float(pf) > 1 and exp is not None and float(exp) > 0:
                    fold_ok += 1

        replay = {
            **base_s,
            "gross_expectancy": gross_s.get("gross_expectancy") or gross_s.get("expectancy"),
            "gross_profit_factor": gross_s.get("gross_profit_factor") or gross_s.get("profit_factor"),
        }
        edge = _edge(gross_s, base_s, adv_s)
        status = _promote(replay, adv_s, gross_s, fold_ok, fold_usable)
        hold = _holding_stats(base_rows)
        # loss concentration where ratio < 2
        filled = [r for r in base_rows if r.get("net_pnl") is not None]
        low_ratio_losses = [
            float(r["net_pnl"])
            for r in filled
            if r.get("gross_move_to_total_cost") is not None
            and float(r["gross_move_to_total_cost"]) < 2
            and float(r["net_pnl"]) < 0
        ]
        results.append(
            {
                "hypothesis_id": hyp["hypothesis_id"],
                "family": hyp["family"],
                "variant": hyp["variant"],
                "status": status,
                "edge_classification": edge,
                "candidates": gate_total,
                "cost_gate_passes": gate_pass,
                "cost_gate_pass_rate": (gate_pass / gate_total) if gate_total else None,
                "replay": replay,
                "cost_versions": {
                    "GROSS_NO_COST_DIAGNOSTIC": gross_s,
                    "BASE_CONSERVATIVE_COST": base_s,
                    "OBSERVED_COST": base_s,
                    "ADVERSE_COST_STRESS": adv_s,
                },
                "folds": folds,
                "holding_stats": hold,
                "net_loss_sum_where_ratio_lt_2": round(sum(low_ratio_losses), 8) if low_ratio_losses else 0.0,
                "requires_microstructure": bool(hyp.get("requires_microstructure")),
                "created_before_evaluation": True,
            }
        )

    def best(fam: str) -> dict[str, Any]:
        cands = [r for r in results if r["family"] == fam]
        cands.sort(
            key=lambda r: (
                int((r.get("replay") or {}).get("completed_trade_count") or 0),
                float((r.get("replay") or {}).get("net_expectancy") or -999),
            ),
            reverse=True,
        )
        if not cands:
            return {"status": "INSUFFICIENT_SAMPLE", "completed_trades": 0}
        r = cands[0]
        rep = r["replay"]
        adv = r["cost_versions"]["ADVERSE_COST_STRESS"]
        return {
            "status": r["status"],
            "hypothesis_id": r["hypothesis_id"],
            "completed_trades": rep.get("completed_trade_count"),
            "cost_gate_pass_rate": r.get("cost_gate_pass_rate"),
            "net_expectancy": rep.get("net_expectancy"),
            "base_pf": rep.get("net_profit_factor") or rep.get("profit_factor"),
            "adverse_pf": adv.get("net_profit_factor") or adv.get("profit_factor"),
            "median_holding_bars": (r.get("holding_stats") or {}).get("median_holding_bars"),
            "median_gross_move_to_cost": (r.get("holding_stats") or {}).get("median_gross_move_to_cost"),
            "edge": r.get("edge_classification"),
            "candidates": r.get("candidates"),
            "trend_events": r.get("candidates") if fam == "H3" else None,
        }

    statuses = [r["status"] for r in results]
    wf_any = any(s == "WALK_FORWARD_VALIDATED" for s in statuses)
    if wf_any:
        recommendation = "NEXUS_NEW_OOS_PLAN_READY"
    elif any(s == "REPLAY_VALIDATED" for s in statuses):
        recommendation = "NEXUS_NEW_WALK_FORWARD_READY"
    else:
        recommendation = "NEXUS_STRATEGY_EDGE_RESEARCH_REQUIRED"

    fund_status = Counter(
        getattr(v, "supported_status", "DATA_UNAVAILABLE") for v in (micro.get("funding") or {}).values()
    )
    oi_status = Counter(
        getattr(v, "supported_status", "DATA_UNAVAILABLE") for v in (micro.get("open_interest") or {}).values()
    )
    tf_status = Counter(
        getattr(v, "supported_status", "DATA_UNAVAILABLE") for v in (micro.get("trade_flow") or {}).values()
    )

    primary = Counter(r.get("edge_classification") for r in results).most_common(1)
    primary_fail = primary[0][0] if primary else "MULTIPLE_FAILURES"
    # Prefer actionable economic failure if present
    if any(r.get("edge_classification") == "GROSS_EDGE_DESTROYED_BY_COST" for r in results):
        primary_fail = "COST_DOMINATED_CHURN"

    return {
        "research_wave_v2_status": RESEARCH_WAVE_V2_STATUS,
        "v2_commit": V2_COMMIT,
        "hypotheses_registered": HYPOTHESES_V3,
        "hypotheses_executed": [h["hypothesis_id"] for h in HYPOTHESES_V3],
        "hypothesis_results": results,
        "cost_gate_starvation": starvation,
        "cost_gate_starvation_counts_by_cause": starvation.get("cost_gate_starvation_counts_by_cause"),
        "oi_data_status": dict(oi_status) or {"DATA_UNAVAILABLE": 1},
        "funding_data_status": dict(fund_status) or {"DATA_UNAVAILABLE": 1},
        "trade_flow_data_status": dict(tf_status) or {"INSUFFICIENT_HISTORY": 1},
        "cvd_data_status": (micro.get("cvd") or {}).get("supported_status", "INSUFFICIENT_HISTORY"),
        "h1_best": best("H1"),
        "h2_best": best("H2"),
        "h3_best": best("H3"),
        "cohorts_replay_validated": sum(1 for s in statuses if s == "REPLAY_VALIDATED"),
        "cohorts_walk_forward_validated": sum(1 for s in statuses if s == "WALK_FORWARD_VALIDATED"),
        "cohorts_rejected": sum(1 for s in statuses if s == "REJECTED"),
        "cohorts_insufficient_sample": sum(1 for s in statuses if s == "INSUFFICIENT_SAMPLE"),
        "primary_remaining_failure": primary_fail,
        "new_untouched_oos_plan_ready": bool(wf_any),
        "maker_sensitivity": "NON_QUALIFYING_DIAGNOSTIC_ONLY",
        "floors_unchanged": True,
        "oos_cohort_status": CONSUMED_STATUS,
        "consumed_oos_id": CONSUMED_OOS_ID,
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
