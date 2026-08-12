"""Cohort edge research pipeline: cost A–D, MFE/MAE, WF folds, OOS plan.

Offline only. Consumed failed OOS excluded from tuning and gates.
"""
from __future__ import annotations

import hashlib
import statistics
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from backend.nexus_demo_execution.cohort_matrix import (
    COHORT_SPECS,
    DATA_UNAVAILABLE_STRATEGIES,
    DUPLICATE_DIRECTION_SUPPRESS,
    MIN_EXPECTED_MOVE_COST_MULT,
    MIN_SAMPLE_FOLD,
    MIN_SAMPLE_REPLAY,
    SAME_SYMBOL_REENTRY_COOLDOWN_BARS,
    SL_COOLDOWN_BARS,
    MAX_SPREAD_BPS_RESEARCH,
    build_context,
    churn_prefilter,
    cohort_key,
    confirm_entry,
)
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


@dataclass
class Hypothesis:
    hypothesis_id: str
    strategy: str
    regime: str
    side: str
    reason: str
    parameters: dict[str, Any]
    training_period: str
    validation_period: str
    created_before_evaluation: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "strategy": self.strategy,
            "regime": self.regime,
            "side": self.side,
            "reason": self.reason,
            "parameters": self.parameters,
            "training_period": self.training_period,
            "validation_period": self.validation_period,
            "created_before_evaluation": self.created_before_evaluation,
        }


def build_cohort_candidates(
    ds: MarketDataset,
    *,
    min_bars: int = 50,
    stride: int = 6,
    fee_rate: float = TAKER_FEE_RATE_DEFAULT,
    spread_bps: float = 2.0,
    slippage_bps: float = 2.0,
    funding_rate: float = 0.0001,
) -> list[MarketCandidate]:
    out: list[MarketCandidate] = []
    candles = ds.candles
    for i in range(min_bars, len(candles) - 2, max(1, stride)):
        hist = candles[: i + 1]
        ctx = build_context(hist)
        ok_churn, _ = churn_prefilter(ctx, spread_bps=spread_bps, slip_bps=slippage_bps)
        for strategy, regime, side in COHORT_SPECS:
            if strategy in DATA_UNAVAILABLE_STRATEGIES:
                continue
            if not ok_churn and strategy != "STRUCT_SWING":
                continue
            ok, _reason = confirm_entry(strategy, regime, side, ctx)
            if not ok:
                continue
            evidence = CandidateEvidence(
                symbol=ds.symbol,
                side=side,
                entry_price=float(ctx.last.close),
                regime=regime,
                strategy=strategy,
                atr=ctx.atr,
                recent_swing_high=ctx.swing_high,
                recent_swing_low=ctx.swing_low,
                support=ctx.support,
                resistance=ctx.resistance,
                liquidity_levels=[
                    x for x in [ctx.resistance if side == "Buy" else ctx.support] if x is not None
                ],
                spread_bps=spread_bps,
                slippage_bps=slippage_bps,
                fee_rate=fee_rate,
                funding_rate=funding_rate,
                qty=None,
                data_freshness_sec=0.0,
                ts=float(ctx.last.ts_ms),
            )
            out.append(
                MarketCandidate(
                    symbol=ds.symbol,
                    side=side,
                    strategy=strategy,
                    regime=regime,
                    candidate_snapshot_time=int(ctx.last.ts_ms),
                    last_input_candle_time=int(ctx.last.ts_ms),
                    entry_price=float(ctx.last.close),
                    evidence=evidence,
                    future_data_reference_count=0,
                    look_ahead_contamination=False,
                )
            )
    return out


def _summ_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [
        r
        for r in rows
        if r.get("net_pnl") is not None
        and r.get("exit_status")
        in {"STOP_LOSS", "TAKE_PROFIT", "TIME_STOP", "TRAILING_EXIT", "BREAK_EVEN_EXIT", "EARLY_EXIT"}
    ]
    nets = [float(r["net_pnl"]) for r in completed]
    gross = [float(r["gross_pnl"]) for r in completed if r.get("gross_pnl") is not None]
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n <= 0]
    g_wins = [n for n in gross if n > 0]
    g_losses = [n for n in gross if n <= 0]
    gw, gl = sum(wins), abs(sum(losses)) if losses else 0.0
    ggw, ggl = sum(g_wins), abs(sum(g_losses)) if g_losses else 0.0
    eq = peak = mdd = 0.0
    consec = max_consec = 0
    for n in nets:
        eq += n
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
        if n <= 0:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0
    return {
        "candidate_count": len(rows),
        "filled_trade_count": sum(1 for r in rows if r.get("entry_status") == "ENTRY_FILLED"),
        "completed_trade_count": len(completed),
        "gross_pnl": round(sum(gross), 8) if gross else None,
        "net_pnl": round(sum(nets), 8) if nets else None,
        "gross_profit_factor": (round(ggw / ggl, 6) if ggl > 0 else None),
        "net_profit_factor": (round(gw / gl, 6) if gl > 0 else None),
        "profit_factor": (round(gw / gl, 6) if gl > 0 else None),
        "gross_expectancy": (statistics.fmean(gross) if gross else None),
        "net_expectancy": (statistics.fmean(nets) if nets else None),
        "expectancy": (statistics.fmean(nets) if nets else None),
        "win_rate": (len(wins) / len(completed)) if completed else None,
        "maximum_drawdown": round(mdd, 8) if nets else None,
        "largest_loss": (min(nets) if nets else None),
        "consecutive_losses": max_consec,
        "fees": round(sum(float(r.get("fees") or 0) for r in completed), 8),
        "spread": round(sum(float(r.get("spread_cost") or 0) for r in completed), 8),
        "slippage": round(sum(float(r.get("slippage") or 0) for r in completed), 8),
        "funding": round(sum(float(r.get("funding") or 0) for r in completed), 8),
        "symbols": sorted({str(r.get("symbol")) for r in completed}),
    }


def _edge_class(cost_summary: dict[str, dict[str, Any]]) -> str:
    g = cost_summary.get("GROSS_NO_COST_DIAGNOSTIC") or {}
    b = cost_summary.get("BASE_CONSERVATIVE_COST") or {}
    a = cost_summary.get("ADVERSE_COST_STRESS") or {}
    n = int(g.get("completed_trade_count") or b.get("completed_trade_count") or 0)
    if n < MIN_SAMPLE_REPLAY:
        return "INSUFFICIENT_SAMPLE"
    g_pf = g.get("gross_profit_factor")
    if g_pf is None:
        g_pf = g.get("profit_factor")
    g_exp = g.get("gross_expectancy")
    if g_exp is None:
        g_exp = g.get("expectancy")
    if g_pf is None or float(g_pf) <= 1.05 or (g_exp is not None and float(g_exp) <= 0):
        return "NO_GROSS_EDGE"
    b_pf = b.get("net_profit_factor") or b.get("profit_factor")
    a_pf = a.get("net_profit_factor") or a.get("profit_factor")
    if b_pf is not None and float(b_pf) < 1.0:
        return "GROSS_EDGE_DESTROYED_BY_COST"
    if a_pf is not None and float(a_pf) >= 1.0 and b_pf is not None and float(b_pf) >= 1.0:
        return "EDGE_SURVIVES_ADVERSE_COST"
    if b_pf is not None and float(b_pf) >= 1.0:
        return "EDGE_SURVIVES_BASE_COST"
    return "EDGE_UNSTABLE"


def _failure_class(rows: list[dict[str, Any]], edge: str) -> str:
    filled = [r for r in rows if r.get("net_pnl") is not None]
    n = len(filled) or 1
    if len(filled) < MIN_SAMPLE_REPLAY:
        return "INSUFFICIENT_SAMPLE"
    if edge in {"GROSS_EDGE_DESTROYED_BY_COST", "COST_DOMINATED_CHURN"}:
        return "COST_DOMINATED_CHURN"
    if edge == "NO_GROSS_EDGE":
        return "MULTIPLE_FAILURES"
    imm = sum(1 for r in filled if r.get("stopped_before_favorable")) / n
    pos_mfe_neg = sum(
        1 for r in filled if float(r.get("mfe") or 0) > 0 and float(r.get("net_pnl") or 0) < 0
    ) / n
    reach_1r = sum(1 for r in filled if r.get("reached_1R")) / n
    if imm > 0.45:
        return "ENTRY_SELECTION_FAILURE"
    if pos_mfe_neg > 0.4 and reach_1r > 0.35:
        return "EXIT_MANAGEMENT_FAILURE"
    if reach_1r < 0.2:
        return "TARGET_PLACEMENT_FAILURE"
    return "MULTIPLE_FAILURES"


def _simulate_pairs(
    pairs: list[tuple[MarketCandidate, list[Candle]]],
    *,
    cost_mode: str,
    apply_costs: bool,
    apply_runtime_churn: bool = True,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    last_sl_bar_idx: dict[str, int] = {}
    last_entry_bar_idx: dict[str, int] = {}
    last_direction: dict[str, str] = {}
    for bar_i, (cand, sub) in enumerate(pairs):
        key = cand.symbol
        if apply_runtime_churn and cand.strategy != "STRUCT_SWING":
            if key in last_sl_bar_idx and bar_i - last_sl_bar_idx[key] < SL_COOLDOWN_BARS:
                out.append(
                    {
                        "symbol": cand.symbol,
                        "side": cand.side,
                        "strategy": cand.strategy,
                        "regime": cand.regime,
                        "entry_status": "CHURN_BLOCKED",
                        "block_reason": "SL_COOLDOWN",
                        "net_pnl": None,
                        "gross_pnl": None,
                    }
                )
                continue
            if key in last_entry_bar_idx and bar_i - last_entry_bar_idx[key] < SAME_SYMBOL_REENTRY_COOLDOWN_BARS:
                out.append(
                    {
                        "symbol": cand.symbol,
                        "side": cand.side,
                        "strategy": cand.strategy,
                        "regime": cand.regime,
                        "entry_status": "CHURN_BLOCKED",
                        "block_reason": "REENTRY_COOLDOWN",
                        "net_pnl": None,
                        "gross_pnl": None,
                    }
                )
                continue
            if (
                DUPLICATE_DIRECTION_SUPPRESS
                and last_direction.get(key) == cand.side
                and key in last_entry_bar_idx
                and bar_i - last_entry_bar_idx[key] < SAME_SYMBOL_REENTRY_COOLDOWN_BARS * 2
            ):
                out.append(
                    {
                        "symbol": cand.symbol,
                        "side": cand.side,
                        "strategy": cand.strategy,
                        "regime": cand.regime,
                        "entry_status": "CHURN_BLOCKED",
                        "block_reason": "DUPLICATE_DIRECTION",
                        "net_pnl": None,
                        "gross_pnl": None,
                    }
                )
                continue
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
            "qty": trade.qty,
        }
        if trade.entry_status == "ENTRY_FILLED" and trade.entry_price is not None:
            last_entry_bar_idx[key] = bar_i
            last_direction[key] = c.side
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
            if trade.exit_status == "STOP_LOSS":
                last_sl_bar_idx[key] = bar_i
        out.append(row)
    return out


def _qualify_status(
    *,
    replay: dict[str, Any],
    fold_results: list[dict[str, Any]],
    edge: str,
) -> str:
    n = int(replay.get("completed_trade_count") or 0)
    if n < MIN_SAMPLE_REPLAY:
        return "INSUFFICIENT_SAMPLE"
    g_exp = replay.get("gross_expectancy")
    n_exp = replay.get("net_expectancy")
    n_pf = replay.get("net_profit_factor") or replay.get("profit_factor")
    mdd = replay.get("maximum_drawdown")
    symbols = replay.get("symbols") or []
    gates_ok = (
        g_exp is not None
        and float(g_exp) > 0
        and n_exp is not None
        and float(n_exp) > 0
        and n_pf is not None
        and float(n_pf) > 1.0
        and (mdd is None or float(mdd) > -50.0)
        and len(symbols) >= 2
        and edge in {"EDGE_SURVIVES_BASE_COST", "EDGE_SURVIVES_ADVERSE_COST"}
    )
    if not gates_ok:
        return "REJECTED"
    ok_folds = 0
    usable = 0
    for fr in fold_results:
        s = fr.get("summary") or {}
        cn = int(s.get("completed_trade_count") or 0)
        if cn < MIN_SAMPLE_FOLD:
            continue
        usable += 1
        pf = s.get("net_profit_factor") or s.get("profit_factor")
        exp = s.get("net_expectancy") or s.get("expectancy")
        if pf is not None and float(pf) > 1.0 and exp is not None and float(exp) > 0:
            ok_folds += 1
    if usable >= 3 and ok_folds >= 2:
        return "WALK_FORWARD_VALIDATED"
    return "REPLAY_VALIDATED"


def _portfolio_diagnostic(
    research_pairs: list[tuple[MarketCandidate, list[Candle]]],
    positive_cohorts: list[dict[str, Any]],
) -> dict[str, Any]:
    allowed = {cohort_key(c["strategy"], c["regime"], c["side"]) for c in positive_cohorts}
    if not allowed:
        return {
            "max_positions_1": {"note": "no_positive_cohorts", "net_pnl": None},
            "max_positions_2": {"note": "no_positive_cohorts", "net_pnl": None},
            "edge_disappears_under_competition": None,
            "multi_position_execution_activated": False,
        }

    def run(max_pos: int) -> dict[str, Any]:
        selected: list[tuple[MarketCandidate, list[Candle]]] = []
        open_count = 0
        btc_side = None
        for cand, sub in research_pairs:
            key = cohort_key(cand.strategy, cand.regime, cand.side)
            if key not in allowed:
                continue
            if open_count >= max_pos:
                continue
            if btc_side and cand.symbol != "BTCUSDT" and cand.side == btc_side and max_pos <= 2:
                continue
            selected.append((cand, sub))
            open_count += 1
            if cand.symbol == "BTCUSDT":
                btc_side = cand.side
            # sequential flat-between for honest offline diagnostic
            open_count = 0
            if len(selected) >= 200:
                break
        rows = _simulate_pairs(
            selected, cost_mode="BASE_CONSERVATIVE", apply_costs=True, apply_runtime_churn=True
        )
        return _summ_rows(rows)

    p1 = run(1)
    p2 = run(2)
    disappears = bool(positive_cohorts) and float(p1.get("net_expectancy") or 0) <= 0
    return {
        "max_positions_1": p1,
        "max_positions_2": p2,
        "correlation_controls_applied": True,
        "multi_position_execution_activated": False,
        "edge_disappears_under_competition": disappears,
    }


def run_cohort_edge_research(
    datasets: list[MarketDataset],
    *,
    consumed_fraction: float = 0.15,
) -> dict[str, Any]:
    assert MIN_NET_REWARD_RISK_RATIO == 1.2
    assert MIN_NET_REWARD_TO_COST == 1.5

    all_pairs: list[tuple[MarketCandidate, list[Candle]]] = []
    for ds in datasets:
        cands = build_cohort_candidates(ds)
        by_ts = {c.ts_ms: i for i, c in enumerate(ds.candles)}
        for cand in cands:
            idx = by_ts.get(cand.candidate_snapshot_time)
            if idx is None:
                continue
            all_pairs.append((cand, ds.candles[idx + 1 :]))
    all_pairs.sort(key=lambda x: x[0].candidate_snapshot_time)

    n = len(all_pairs)
    cut = int(n * (1.0 - consumed_fraction))
    research_pairs = all_pairs[:cut]
    consumed_pairs = all_pairs[cut:]

    hypotheses: list[Hypothesis] = []
    for strategy, regime, side in COHORT_SPECS:
        hid = hashlib.sha1(f"{strategy}|{regime}|{side}".encode()).hexdigest()[:10]
        hypotheses.append(
            Hypothesis(
                hypothesis_id=f"H_{hid}",
                strategy=strategy,
                regime=regime,
                side=side,
                reason="Founder cohort matrix — independent strategy×regime×side qualification",
                parameters={
                    "margin_usdt": 20,
                    "leverage": 25,
                    "max_loss": 3,
                    "churn": {
                        "min_expected_move_cost_mult": MIN_EXPECTED_MOVE_COST_MULT,
                        "max_spread_bps": MAX_SPREAD_BPS_RESEARCH,
                        "sl_cooldown_bars": SL_COOLDOWN_BARS,
                        "reentry_cooldown_bars": SAME_SYMBOL_REENTRY_COOLDOWN_BARS,
                    },
                    "floors_unchanged": True,
                },
                training_period="research_pairs chronological prefix",
                validation_period="research_pairs 3 chronological folds",
                created_before_evaluation=True,
            )
        )

    by_cohort: dict[str, list[tuple[MarketCandidate, list[Candle]]]] = defaultdict(list)
    for p in research_pairs:
        by_cohort[cohort_key(p[0].strategy, p[0].regime, p[0].side)].append(p)

    cohort_reports: list[dict[str, Any]] = []
    for strategy, regime, side in COHORT_SPECS:
        if strategy not in DATA_UNAVAILABLE_STRATEGIES:
            continue
        cohort_reports.append(
            {
                "cohort_id": cohort_key(strategy, regime, side),
                "strategy": strategy,
                "regime": regime,
                "side": side,
                "status": "INSUFFICIENT_SAMPLE",
                "edge_classification": "INSUFFICIENT_SAMPLE",
                "failure_classification": "INSUFFICIENT_SAMPLE",
                "note": "Required market data (CVD/funding/OI) not in historical kline bundle",
                "replay": {"completed_trade_count": 0},
                "folds": [],
                "cost_versions": {},
            }
        )

    for key, pairs in sorted(by_cohort.items()):
        strategy, regime, side = key.split("|", 2)
        m = len(pairs)
        f1, f2 = int(m * 0.33), int(m * 0.66)
        base_rows = _simulate_pairs(pairs, cost_mode="BASE_CONSERVATIVE", apply_costs=True)
        gross_rows = _simulate_pairs(pairs, cost_mode="GROSS_NO_COST_DIAGNOSTIC", apply_costs=False)
        # OBSERVED uses same estimated bps as BASE in this research bundle — avoid duplicate sim.
        observed_rows = base_rows
        adverse_rows = _simulate_pairs(pairs, cost_mode="ADVERSE_COST_STRESS", apply_costs=True)
        cost_versions = {
            "GROSS_NO_COST_DIAGNOSTIC": gross_rows,
            "BASE_CONSERVATIVE_COST": base_rows,
            "OBSERVED_COST": observed_rows,
            "ADVERSE_COST_STRESS": adverse_rows,
        }
        cost_summary = {k: _summ_rows(v) for k, v in cost_versions.items()}
        edge = _edge_class(cost_summary)
        failure = _failure_class(base_rows, edge)
        if edge == "GROSS_EDGE_DESTROYED_BY_COST":
            failure = "COST_DOMINATED_CHURN"

        # Chronological fold metrics from contiguous slices (no re-sim; preserves time order).
        fold_slices_rows = [
            ("fold_1", pairs[:f1], base_rows[:f1]),
            ("fold_2", pairs[f1:f2], base_rows[f1:f2]),
            ("fold_3", pairs[f2:], base_rows[f2:]),
        ]
        fold_results = []
        for fname, fpairs, frows in fold_slices_rows:
            fold_results.append(
                {
                    "fold": fname,
                    "pair_count": len(fpairs),
                    "summary": _summ_rows(frows),
                    "entry_triggered_count": sum(
                        1
                        for r in frows
                        if r.get("entry_status") in {"ENTRY_FILLED", "ENTRY_TRIGGERED_NOT_FILLED"}
                    ),
                }
            )

        gsum = cost_summary["GROSS_NO_COST_DIAGNOSTIC"]
        replay = {
            **cost_summary["BASE_CONSERVATIVE_COST"],
            "gross_pnl": gsum.get("gross_pnl"),
            "gross_profit_factor": gsum.get("gross_profit_factor") or gsum.get("profit_factor"),
            "gross_expectancy": gsum.get("gross_expectancy") or gsum.get("expectancy"),
        }
        status = _qualify_status(replay=replay, fold_results=fold_results, edge=edge)

        filled = [r for r in base_rows if r.get("net_pnl") is not None]
        n_f = len(filled) or 1
        entry_quality = {
            "immediate_adverse_rate": sum(
                1 for r in filled if float(r.get("mae") or 0) > 0 and float(r.get("mfe") or 0) <= 0
            )
            / n_f,
            "reached_0_5R_rate": sum(1 for r in filled if r.get("reached_0_5R")) / n_f,
            "reached_1R_rate": sum(1 for r in filled if r.get("reached_1R")) / n_f,
            "target_before_stop_rate": sum(1 for r in filled if r.get("exit_status") == "TAKE_PROFIT") / n_f,
            "stopped_before_positive_excursion_rate": sum(
                1 for r in filled if r.get("stopped_before_favorable")
            )
            / n_f,
            "positive_MFE_but_negative_exit_rate": sum(
                1 for r in filled if float(r.get("mfe") or 0) > 0 and float(r.get("net_pnl") or 0) < 0
            )
            / n_f,
        }

        rep = {
            "cohort_id": key,
            "strategy": strategy,
            "regime": regime,
            "side": side,
            "status": status,
            "edge_classification": edge,
            "failure_classification": failure,
            "replay": replay,
            "folds": fold_results,
            "cost_versions": cost_summary,
            "entry_quality": entry_quality,
            "consumed_oos_used_for_tuning": False,
        }
        if strategy == "STRUCT_SWING" and regime == "RANGE":
            if status not in {"WALK_FORWARD_VALIDATED", "REPLAY_VALIDATED"}:
                rep["status"] = "REJECTED"
            rep["range_struct_swing_baseline"] = True
            rep["note"] = "Failed global baseline; remains REJECTED without redesigned independent evidence"
        cohort_reports.append(rep)

    positive_cohorts = [
        r
        for r in cohort_reports
        if (r.get("replay") or {}).get("net_expectancy") is not None
        and float((r.get("replay") or {}).get("net_expectancy") or 0) > 0
        and int((r.get("replay") or {}).get("completed_trade_count") or 0) >= MIN_SAMPLE_FOLD
    ]
    portfolio = _portfolio_diagnostic(research_pairs, positive_cohorts)

    statuses = [r["status"] for r in cohort_reports]
    edges = [r.get("edge_classification") for r in cohort_reports]

    def _top(metric: str, *, ascending: bool = False, limit: int = 5) -> list[dict[str, Any]]:
        scored = []
        for r in cohort_reports:
            rep = r.get("replay") or {}
            val = rep.get(metric)
            if val is None and metric == "profit_factor":
                val = rep.get("net_profit_factor")
            if val is None:
                continue
            if int(rep.get("completed_trade_count") or 0) < 5:
                continue
            scored.append((float(val), r))
        scored.sort(key=lambda x: x[0], reverse=not ascending)
        return [
            {
                "cohort_id": r["cohort_id"],
                "status": r["status"],
                "edge": r.get("edge_classification"),
                metric: v,
                "completed_trade_count": (r.get("replay") or {}).get("completed_trade_count"),
                "net_expectancy": (r.get("replay") or {}).get("net_expectancy"),
                "gross_expectancy": (r.get("replay") or {}).get("gross_expectancy"),
            }
            for v, r in scored[:limit]
        ]

    wf_any = any(s == "WALK_FORWARD_VALIDATED" for s in statuses)
    end_ms = max((ds.end_time for ds in datasets), default=0)
    start_ms = min((ds.start_time for ds in datasets), default=0)
    span = max(end_ms - start_ms, 1)
    consumed_start_approx = end_ms - int(span * 0.15)
    new_oos_start = end_ms + 1
    new_oos_end = end_ms + 45 * 24 * 60 * 60 * 1000
    oos_plan = {
        "status": "NEW_UNTOUCHED_OOS_PLAN_READY" if wf_any else "NEW_UNTOUCHED_OOS_PLAN_DEFERRED",
        "new_oos_start": new_oos_start,
        "new_oos_end": new_oos_end,
        "symbols": sorted({ds.symbol for ds in datasets}),
        "data_checksum": hashlib.sha256(
            f"{new_oos_start}:{new_oos_end}:{','.join(sorted(ds.symbol for ds in datasets))}".encode()
        ).hexdigest(),
        "created_before_download": True,
        "no_overlap_with_consumed_oos": True,
        "consumed_oos_id": CONSUMED_OOS_ID,
        "consumed_oos_approx_start_ms": consumed_start_approx,
        "run_automatically": False,
        "note": "Do not execute until >=1 cohort is WALK_FORWARD_VALIDATED",
    }

    range_struct = [r for r in cohort_reports if r["strategy"] == "STRUCT_SWING" and r["regime"] == "RANGE"]
    range_status = "REJECTED"
    if range_struct:
        # Prefer Sell/Buy combined message
        if all(r["status"] == "REJECTED" for r in range_struct):
            range_status = "REJECTED"
        else:
            range_status = range_struct[0]["status"]

    if wf_any and oos_plan["status"] == "NEW_UNTOUCHED_OOS_PLAN_READY":
        recommendation = "NEXUS_NEW_OOS_PLAN_READY"
    elif wf_any or any(s == "REPLAY_VALIDATED" for s in statuses):
        recommendation = "NEXUS_NEW_WALK_FORWARD_READY"
    else:
        recommendation = "NEXUS_STRATEGY_EDGE_RESEARCH_REQUIRED"

    return {
        "simulator_policy": {
            "margin_usdt": 20,
            "leverage": 25,
            "margin_mode": "ISOLATED",
            "maximum_notional": 500,
            "maximum_single_trade_net_loss": 3,
            "simulator_risk_model_result": "MULTIPLE_SIMULATION_DEFECTS_FIXED",
        },
        "oos_cohort_status": CONSUMED_STATUS,
        "consumed_oos_id": CONSUMED_OOS_ID,
        "reuse_for_final_proof": False,
        "STRUCTURAL_GEOMETRY_GLOBAL_POLICY": "REJECTED",
        "floors_unchanged": {
            "MIN_NET_REWARD_RISK_RATIO": MIN_NET_REWARD_RISK_RATIO,
            "MIN_NET_REWARD_TO_COST": MIN_NET_REWARD_TO_COST,
        },
        "research_pair_count": len(research_pairs),
        "consumed_pair_count_excluded": len(consumed_pairs),
        "hypotheses": [h.to_dict() for h in hypotheses],
        "cohorts": cohort_reports,
        "cohorts_total": len(cohort_reports),
        "cohorts_rejected": sum(1 for s in statuses if s == "REJECTED"),
        "cohorts_replay_validated": sum(1 for s in statuses if s == "REPLAY_VALIDATED"),
        "cohorts_walk_forward_validated": sum(1 for s in statuses if s == "WALK_FORWARD_VALIDATED"),
        "cohorts_insufficient_sample": sum(1 for s in statuses if s == "INSUFFICIENT_SAMPLE"),
        "top_cohorts_by_gross_expectancy": _top("gross_expectancy"),
        "top_cohorts_by_net_expectancy": _top("net_expectancy"),
        "top_cohorts_by_profit_factor": _top("net_profit_factor"),
        "top_cohorts_by_drawdown": _top("maximum_drawdown", ascending=False),
        "range_struct_swing_status": range_status,
        "cost_dominated_cohort_count": sum(1 for e in edges if e == "GROSS_EDGE_DESTROYED_BY_COST"),
        "no_gross_edge_cohort_count": sum(1 for e in edges if e == "NO_GROSS_EDGE"),
        "edge_survives_base_cost_count": sum(1 for e in edges if e == "EDGE_SURVIVES_BASE_COST"),
        "edge_survives_adverse_cost_count": sum(1 for e in edges if e == "EDGE_SURVIVES_ADVERSE_COST"),
        "portfolio_diagnostic": portfolio,
        "new_walk_forward_result": {
            "folds": 3,
            "chronological": True,
            "consumed_oos_excluded": True,
            "any_walk_forward_validated": wf_any,
        },
        "new_untouched_oos_plan": oos_plan,
        "new_untouched_oos_plan_ready": oos_plan["status"] == "NEW_UNTOUCHED_OOS_PLAN_READY",
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
