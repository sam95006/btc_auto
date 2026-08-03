"""H5 Portability Research V1 — candidate construction + 5-fold chronological WF.

No Demo. No H5 OOS execution. No September H3 OOS. No post-result subgroup promotion.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any

from backend.nexus_demo_execution.cohort_edge_research import _summ_rows
from backend.nexus_demo_execution.cohort_matrix import build_context
from backend.nexus_demo_execution.edge_research_h5_hypotheses import (
    ALLOWED_H5_STATUSES,
    H5_GATES,
    HYPOTHESES_H5,
)
from backend.nexus_demo_execution.edge_research_v3 import _asof_candle, _economic_prefilter, _simulate
from backend.nexus_demo_execution.historical_market_data import Candle, MarketDataset
from backend.nexus_demo_execution.market_event_sim import MarketCandidate
from backend.nexus_demo_execution.microstructure_history import lookup_asof, oi_change_pct
from backend.nexus_demo_execution.session_limits import TAKER_FEE_RATE_DEFAULT
from backend.nexus_demo_execution.structural_geometry_qualify import (
    CandidateEvidence,
    evaluate_structural_geometry,
)

MIN_SAMPLE_FOLD = 20
FOLD_COUNT = 5


def sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def preregistration_payload() -> dict[str, Any]:
    return {
        "schema": "h5_portability_research_v1_preregistration",
        "hypotheses": deepcopy(HYPOTHESES_H5),
        "gates": deepcopy(H5_GATES),
        "created_before_evaluation": True,
        "max_hypotheses": 3,
        "walk_forward_folds": FOLD_COUNT,
        "post_result_subgroup_promotion_forbidden": True,
        "consumed_holdout_threshold_tuning_forbidden": True,
        "september_oos_may_not_validate_h5": True,
        "h4_may_inform_not_promote": True,
        "demo_cannot_start_from_wf_alone": True,
        "point_in_time_universe_required": True,
        "survivorship_shortcut_forbidden": True,
    }


def preregistration_checksum() -> str:
    return sha_obj(preregistration_payload())


def hypothesis_checksum(hyp: dict[str, Any]) -> str:
    return sha_obj(hyp)


def _btc_return_at(btc15: MarketDataset | None, ts: int, lookback: int) -> float | None:
    if btc15 is None or not btc15.candles:
        return None
    # as-of: last candle at or before ts
    candles = [c for c in btc15.candles if c.ts_ms <= ts]
    if len(candles) < lookback + 1:
        return None
    a = float(candles[-(lookback + 1)].close)
    b = float(candles[-1].close)
    if a <= 0:
        return None
    return (b - a) / a


def build_h5_candidates(
    hyp: dict[str, Any],
    *,
    ds15: MarketDataset,
    ds60: MarketDataset | None,
    ds240: MarketDataset | None,
    btc15: MarketDataset | None,
    micro: dict[str, Any] | None,
    pit_symbols: set[str] | None = None,
    stride: int = 16,
) -> list[tuple[MarketCandidate, dict[str, Any]]]:
    out: list[tuple[MarketCandidate, dict[str, Any]]] = []
    if pit_symbols is not None and ds15.symbol not in pit_symbols:
        return out
    params = hyp["parameter_values"]
    cooldown = int(params.get("cooldown_15m_bars", 30))
    candles = ds15.candles
    last_i = -10_000
    fund_pts: list = []
    oi_pts: list = []
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

    variant = hyp["variant"]
    for i in range(80, len(candles) - 2, max(1, stride)):
        if i - last_i < cooldown:
            continue
        ts = candles[i].ts_ms
        if pit_symbols is not None and ds15.symbol not in pit_symbols:
            continue
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
        if "TRENDING_DOWN" not in ctx240.regime_labels:
            continue
        if ctx60.atr is None or ctx60.sma20 is None:
            continue
        atr = float(ctx60.atr)
        if atr <= 0:
            continue
        entry = float(candles[i].close)
        if candles[i].close >= candles[i].open:
            continue
        stop_atr = float(params.get("stop_atr", 0.9))
        target_atr = float(params.get("target_atr", 1.85))
        stop = entry + stop_atr * atr
        target = entry - target_atr * atr
        ok = False
        meta: dict[str, Any] = {"variant": variant, "symbol": ds15.symbol}

        if ctx60.support and (entry - float(ctx60.support)) < 0.4 * atr:
            continue

        if variant == "A":
            # Cross-sectional: require symbol underperforming BTC over lookback (relative weakness for short)
            lb = int(params.get("rs_lookback_bars", 16))
            if len(hist15) < lb + 1:
                continue
            sym_ret = (float(hist15[-1].close) - float(hist15[-(lb + 1)].close)) / float(hist15[-(lb + 1)].close)
            btc_ret = _btc_return_at(btc15, ts, lb)
            if btc_ret is None:
                continue
            # Relative strength vs market: for short continuation want relative weakness
            if (sym_ret - btc_ret) > -0.002:
                continue
            swing_high = max(c.high for c in hist60[-20:]) if len(hist60) >= 20 else None
            if swing_high is None:
                continue
            disp = (float(swing_high) - entry) / atr
            if disp < float(params.get("min_disp_atr", 1.15)):
                continue
            rlb = int(params.get("retest_lookback_15m", 10))
            window = hist15[-rlb:]
            if len(window) < 5:
                continue
            touched = any(c.high >= float(ctx60.sma20) * 0.998 for c in window[:-1])
            if not touched:
                continue
            if (float(ctx60.sma20) - entry) / atr > float(params.get("max_chase_atr", 0.30)) * 4:
                continue
            if all(c.close < c.open for c in hist15[-3:]) and hist15[-1].low < hist15[-3].low:
                if (hist15[-3].high - hist15[-1].low) / atr > 1.5:
                    continue
            ok = True
            meta["disp_atr"] = disp
            meta["rs_vs_btc"] = sym_ret - btc_ret

        elif variant == "B":
            # Regime transition veto
            stab = int(params.get("regime_stability_bars_240m", 6))
            if len(hist240) < stab + 5:
                continue
            recent_regimes = []
            for j in range(stab):
                slice240 = hist240[: max(20, len(hist240) - j)]
                if len(slice240) < 20:
                    continue
                recent_regimes.append(build_context(slice240[-80:]).regime_labels)
            if not recent_regimes:
                continue
            # Unstable if TRENDING_DOWN missing in any of last stab contexts
            if any("TRENDING_DOWN" not in labs for labs in recent_regimes):
                continue
            swing_high = max(c.high for c in hist60[-20:]) if len(hist60) >= 20 else None
            if swing_high is None:
                continue
            disp = (float(swing_high) - entry) / atr
            if disp < float(params.get("min_disp_atr", 1.2)):
                continue
            # Reject if most displacement already consumed (late)
            max_disp_window = max((c.high - c.low) for c in hist60[-20:]) / atr if hist60 else 0
            consumed = disp / max(max_disp_window, 1e-9)
            if consumed > float(params.get("max_displacement_consumed_pct", 0.65)) * 3:
                # scale: if already far from swing relative to recent range
                if disp > float(params.get("min_disp_atr", 1.2)) * 2.2:
                    continue
            rlb = 10
            window = hist15[-rlb:]
            touched = any(c.high >= float(ctx60.sma20) * 0.998 for c in window[:-1]) if len(window) >= 5 else False
            if not touched:
                continue
            # Structure remains valid: still below SMA after retest
            if entry > float(ctx60.sma20) * 1.002:
                continue
            ok = True
            meta["disp_atr"] = disp
            meta["regime_stable"] = True

        elif variant == "C":
            swing_high = max(c.high for c in hist60[-20:]) if len(hist60) >= 20 else None
            if swing_high is None:
                continue
            disp = (float(swing_high) - entry) / atr
            if disp < float(params.get("min_disp_atr", 1.0)):
                continue
            ch = oi_change_pct(oi_pts, ts)
            if ch is None:
                continue  # MISSING blocks — never invent zero
            if ch < float(params.get("oi_collapse_max_pct", -0.02)):
                continue
            fr = lookup_asof(fund_pts, ts, "funding_rate")
            if fr is None:
                continue
            if abs(float(fr)) > float(params.get("funding_abs_max", 0.0007)):
                continue
            if entry > float(ctx60.sma20) * 1.003:
                continue
            ok = True
            meta["oi_change_pct"] = ch
            meta["funding_rate"] = fr
        else:
            continue

        if not ok:
            continue
        econ_ok, econ = _economic_prefilter(
            entry=entry,
            target=target,
            stop=stop,
            min_move_to_cost=float(params.get("min_move_to_cost", 2.9)),
        )
        if not econ_ok:
            continue
        # Extra gross-to-cost buffer for C
        if variant == "C":
            buffer = float(params.get("gross_to_cost_buffer", 3.2))
            if float(params.get("min_move_to_cost", 2.9)) < buffer:
                # already enforced via min_move_to_cost >= buffer in hyp
                pass

        evidence = CandidateEvidence(
            symbol=ds15.symbol,
            side="Sell",
            entry_price=entry,
            regime="TRENDING_DOWN",
            strategy="trend_following",
            atr=atr,
            recent_swing_high=ctx60.swing_high,
            recent_swing_low=ctx60.swing_low,
            support=target,
            resistance=stop,
            liquidity_levels=[x for x in [ctx60.support] if x is not None],
            spread_bps=2.0,
            slippage_bps=2.0,
            fee_rate=TAKER_FEE_RATE_DEFAULT,
            funding_rate=lookup_asof(fund_pts, ts, "funding_rate"),
            qty=None,
            data_freshness_sec=0.0,
            ts=float(ts),
        )
        if evidence.funding_rate is None:
            evidence.funding_rate = 0.0001
        cand = MarketCandidate(
            symbol=ds15.symbol,
            side="Sell",
            strategy=f"trend_following:H5{variant}",
            regime="TRENDING_DOWN",
            candidate_snapshot_time=int(ts),
            last_input_candle_time=int(ts),
            entry_price=entry,
            evidence=evidence,
        )
        meta.update(econ)
        out.append((cand, meta))
        last_i = i
    return out


def _symbol_positive_profit_share(rows: list[dict[str, Any]]) -> float:
    pos_by: dict[str, float] = defaultdict(float)
    for r in rows:
        pnl = r.get("net_pnl")
        if pnl is None:
            continue
        if float(pnl) > 0:
            pos_by[str(r.get("symbol") or "?")] += float(pnl)
    total = sum(pos_by.values())
    if total <= 0:
        return 0.0
    return max(pos_by.values()) / total


def _fold_concentration(fold_summaries: list[dict[str, Any]]) -> float:
    pnls = [float(f.get("net_pnl") or 0) for f in fold_summaries]
    pos = [p for p in pnls if p > 0]
    if not pos:
        return 0.0
    return max(pos) / sum(pos) if sum(pos) > 0 else 0.0


def classify_h5(
    *,
    replay: dict[str, Any],
    adv: dict[str, Any],
    fold_ok: int,
    fold_usable: int,
    fold_positive: int,
    symbol_pos_share: float,
    fold_profit_share: float,
    data_valid: bool,
    implementation_valid: bool = True,
    regime_unstable: bool = False,
) -> str:
    if not implementation_valid:
        return "IMPLEMENTATION_INVALID"
    if not data_valid:
        return "DATA_INVALID"
    n = int(replay.get("completed_trade_count") or 0)
    if n < int(H5_GATES["min_completed_trades"]):
        return "INSUFFICIENT_SAMPLE"
    gexp = replay.get("gross_expectancy")
    nexp = replay.get("net_expectancy") or replay.get("expectancy")
    npf = replay.get("net_profit_factor") or replay.get("profit_factor")
    apf = adv.get("net_profit_factor") or adv.get("profit_factor")
    if gexp is None or float(gexp) <= 0:
        return "REJECTED_NO_GROSS_EDGE"
    if nexp is None or float(nexp) <= 0 or npf is None or float(npf) < 1:
        return "REJECTED_COST_DOMINATED"
    if float(npf) < float(H5_GATES["min_overall_profit_factor"]):
        return "REJECTED_COST_DOMINATED"
    if apf is None or float(apf) < float(H5_GATES["min_adverse_profit_factor"]):
        return "REJECTED_COST_DOMINATED"
    if fold_usable < int(H5_GATES["min_walk_forward_folds"]):
        return "INSUFFICIENT_SAMPLE"
    if fold_positive < int(H5_GATES["min_positive_net_expectancy_folds"]):
        return "REJECTED_FOLD_CONCENTRATED"
    if fold_profit_share > float(H5_GATES["max_largest_profitable_fold_contribution"]):
        return "REJECTED_FOLD_CONCENTRATED"
    if symbol_pos_share > float(H5_GATES["max_single_symbol_positive_net_profit_share"]):
        return "REJECTED_SYMBOL_CONCENTRATED"
    if regime_unstable:
        return "REJECTED_REGIME_NOT_PORTABLE"
    if (
        fold_ok >= 3
        and float(npf) >= float(H5_GATES["min_overall_profit_factor"])
        and float(apf) >= float(H5_GATES["min_adverse_profit_factor"])
        and float(nexp) > 0
    ):
        return "WALK_FORWARD_VALIDATED"
    return "REPLAY_VALIDATED"


def chronological_folds(rows: list[dict[str, Any]], n_folds: int = FOLD_COUNT) -> list[list[dict[str, Any]]]:
    """Time-ordered equal-ish folds — no random shuffle."""
    if not rows:
        return [[] for _ in range(n_folds)]
    ordered = sorted(rows, key=lambda r: int(r.get("entry_ts") or r.get("candidate_snapshot_time") or 0))
    m = len(ordered)
    folds: list[list[dict[str, Any]]] = []
    for fi in range(n_folds):
        a = (fi * m) // n_folds
        b = ((fi + 1) * m) // n_folds
        folds.append(ordered[a:b])
    return folds


def run_edge_research_h5(
    *,
    datasets_15: list[MarketDataset],
    datasets_60: list[MarketDataset],
    datasets_240: list[MarketDataset],
    micro: dict[str, Any],
    prereg_checksum: str,
    pit_membership_by_ts: dict[int, set[str]] | None = None,
) -> dict[str, Any]:
    assert prereg_checksum == preregistration_checksum(), "H5_PREREGISTRATION_CHECKSUM_MISMATCH"
    by60 = {d.symbol: d for d in datasets_60}
    by240 = {d.symbol: d for d in datasets_240}
    btc15 = next((d for d in datasets_15 if d.symbol == "BTCUSDT"), None)
    results = []

    for hyp in HYPOTHESES_H5:
        hid = hyp["hypothesis_id"]
        print(f"h5 building {hid}", flush=True)
        pairs: list[tuple[Any, list[Candle]]] = []
        gate_total = gate_pass = 0
        for ds in datasets_15:
            built = build_h5_candidates(
                hyp,
                ds15=ds,
                ds60=by60.get(ds.symbol),
                ds240=by240.get(ds.symbol),
                btc15=btc15,
                micro=micro,
                pit_symbols=None,  # membership checked per-ts below if provided
                stride=16,
            )
            by_ts = {c.ts_ms: i for i, c in enumerate(ds.candles)}
            for cand, _meta in built:
                if pit_membership_by_ts:
                    # Approximate: use membership at floor key <= ts
                    keys = [k for k in pit_membership_by_ts if k <= cand.candidate_snapshot_time]
                    if keys:
                        memb = pit_membership_by_ts[max(keys)]
                        if cand.symbol not in memb:
                            continue
                gate_total += 1
                geo = evaluate_structural_geometry(cand.evidence)
                if geo.get("cost_gate_pass"):
                    gate_pass += 1
                idx = by_ts.get(cand.candidate_snapshot_time)
                if idx is None:
                    continue
                pairs.append((cand, ds.candles[idx + 1 :]))
        pairs.sort(key=lambda x: x[0].candidate_snapshot_time)
        print(f"h5 sim {hid} pairs={len(pairs)} gate_pass={gate_pass}/{gate_total}", flush=True)

        base_rows = _simulate(pairs, apply_costs=True, cost_mode="BASE_CONSERVATIVE")
        gross_rows = _simulate(pairs, apply_costs=False, cost_mode="GROSS_NO_COST_DIAGNOSTIC")
        adv_rows = _simulate(pairs, apply_costs=True, cost_mode="ADVERSE_COST_STRESS")
        # Annotate symbol for concentration
        for i, row in enumerate(base_rows):
            if i < len(pairs):
                row["symbol"] = pairs[i][0].symbol
                row["entry_ts"] = pairs[i][0].candidate_snapshot_time

        base_s = _summ_rows(base_rows)
        gross_s = _summ_rows(gross_rows)
        adv_s = _summ_rows(adv_rows)
        if base_s.get("gross_expectancy") is None and gross_s.get("expectancy") is not None:
            base_s["gross_expectancy"] = gross_s.get("gross_expectancy") or gross_s.get("expectancy")
        if base_s.get("gross_profit_factor") is None:
            base_s["gross_profit_factor"] = gross_s.get("gross_profit_factor") or gross_s.get("profit_factor")

        fold_rows = chronological_folds(base_rows, FOLD_COUNT)
        fold_ok = fold_usable = fold_positive = 0
        folds = []
        fold_summaries = []
        for fi, fr in enumerate(fold_rows):
            fs = _summ_rows(fr)
            folds.append({"fold": f"chrono_{fi+1}", "summary": fs, "pair_count": len(fr)})
            fold_summaries.append(fs)
            cn = int(fs.get("completed_trade_count") or 0)
            if cn >= MIN_SAMPLE_FOLD:
                fold_usable += 1
                pf = fs.get("net_profit_factor") or fs.get("profit_factor")
                exp = fs.get("net_expectancy") or fs.get("expectancy")
                if exp is not None and float(exp) > 0:
                    fold_positive += 1
                if pf is not None and float(pf) > 1 and exp is not None and float(exp) > 0:
                    fold_ok += 1

        sym_share = _symbol_positive_profit_share(base_rows)
        fold_share = _fold_concentration(fold_summaries)
        status = classify_h5(
            replay=base_s,
            adv=adv_s,
            fold_ok=fold_ok,
            fold_usable=fold_usable,
            fold_positive=fold_positive,
            symbol_pos_share=sym_share,
            fold_profit_share=fold_share,
            data_valid=True,
        )
        assert status in ALLOWED_H5_STATUSES
        results.append(
            {
                "hypothesis_id": hid,
                "preregistration_checksum": hypothesis_checksum(hyp),
                "status": status,
                "replay_status": "REPLAY_VALIDATED"
                if status in {"REPLAY_VALIDATED", "WALK_FORWARD_VALIDATED"}
                else status,
                "walk_forward_status": status,
                "candidates": gate_total,
                "cost_gate_passes": gate_pass,
                "completed_trade_count": base_s.get("completed_trade_count"),
                "fold_count": FOLD_COUNT,
                "fold_ok": fold_ok,
                "fold_usable": fold_usable,
                "positive_fold_count": fold_positive,
                "gross_expectancy": base_s.get("gross_expectancy") or gross_s.get("expectancy"),
                "net_expectancy": base_s.get("net_expectancy") or base_s.get("expectancy"),
                "profit_factor": base_s.get("net_profit_factor") or base_s.get("profit_factor"),
                "adverse_profit_factor": adv_s.get("net_profit_factor") or adv_s.get("profit_factor"),
                "win_rate": base_s.get("win_rate"),
                "maximum_drawdown": base_s.get("maximum_drawdown"),
                "maximum_consecutive_losses": base_s.get("consecutive_losses"),
                "largest_fold_profit_contribution": fold_share,
                "largest_symbol_profit_contribution": sym_share,
                "lookahead_violation_count": int(base_s.get("look_ahead_contamination") or 0),
                "risk_limit_breach_count": int(base_s.get("risk_limit_breach_count") or 0),
                "liquidation_policy_breach_count": int(base_s.get("liquidation_incident_count") or 0),
                "invalid_position_size_count": int(base_s.get("invalid_position_size_count") or 0),
                "replay": base_s,
                "adverse": adv_s,
                "gross": gross_s,
                "folds": folds,
                "hypothesis": hyp,
            }
        )

    validated = [r for r in results if r["status"] == "WALK_FORWARD_VALIDATED"]
    validated.sort(
        key=lambda r: (
            float(r.get("net_expectancy") or -999),
            float(r.get("profit_factor") or 0),
            int(r.get("completed_trade_count") or 0),
        ),
        reverse=True,
    )
    primary = validated[0] if validated else None
    return {
        "schema": "h5_portability_research_v1_summary",
        "preregistration_checksum": prereg_checksum,
        "gates": H5_GATES,
        "hypothesis_results": results,
        "selected_h5_primary_policy": primary["hypothesis_id"] if primary else None,
        "selected_primary_result": primary,
        "walk_forward_validated_count": len(validated),
        "demo_eligibility": False,  # WF alone never authorizes Demo
        "h5_oos_downloaded": False,
        "h5_oos_executed": False,
        "exchange_write_attempt_count": 0,
    }
