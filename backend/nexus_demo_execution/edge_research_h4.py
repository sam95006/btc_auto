"""H4 Edge Research V1 — candidate construction + Replay/WF evaluation.

Does not touch consumed H3 holdout or September OOS as development data.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter
from copy import deepcopy
from typing import Any

from backend.nexus_demo_execution.cohort_edge_research import _summ_rows
from backend.nexus_demo_execution.cohort_matrix import build_context
from backend.nexus_demo_execution.edge_research_h4_hypotheses import H4_GATES, HYPOTHESES_H4
from backend.nexus_demo_execution.edge_research_v3 import _asof_candle, _economic_prefilter, _simulate
from backend.nexus_demo_execution.historical_market_data import Candle, MarketDataset
from backend.nexus_demo_execution.market_event_sim import MarketCandidate
from backend.nexus_demo_execution.microstructure_history import lookup_asof, oi_change_pct
from backend.nexus_demo_execution.session_limits import TAKER_FEE_RATE_DEFAULT
from backend.nexus_demo_execution.structural_geometry_qualify import (
    CandidateEvidence,
    evaluate_structural_geometry,
)

MIN_SAMPLE_FOLD = 8


def sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def preregistration_payload() -> dict[str, Any]:
    return {
        "schema": "h4_edge_research_v1_preregistration",
        "hypotheses": deepcopy(HYPOTHESES_H4),
        "gates": deepcopy(H4_GATES),
        "created_before_evaluation": True,
        "max_hypotheses": 3,
        "post_result_variant_addition_forbidden": True,
        "consumed_holdout_threshold_tuning_forbidden": True,
        "september_oos_may_not_validate_h4": True,
    }


def preregistration_checksum() -> str:
    return sha_obj(preregistration_payload())


def hypothesis_checksum(hyp: dict[str, Any]) -> str:
    return sha_obj(hyp)


def build_h4_candidates(
    hyp: dict[str, Any],
    *,
    ds15: MarketDataset,
    ds60: MarketDataset | None,
    ds240: MarketDataset | None,
    micro: dict[str, Any] | None,
    stride: int = 16,
) -> list[tuple[MarketCandidate, dict[str, Any]]]:
    out: list[tuple[MarketCandidate, dict[str, Any]]] = []
    params = hyp["parameter_values"]
    cooldown = int(params.get("cooldown_15m_bars", 28))
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

    for i in range(80, len(candles) - 2, max(1, stride)):
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
        variant = hyp["variant"]
        stop_atr = float(params.get("stop_atr", 0.9))
        target_atr = float(params.get("target_atr", 1.8))
        stop = entry + stop_atr * atr
        target = entry - target_atr * atr
        ok = False
        meta: dict[str, Any] = {"variant": variant}

        # Shared: avoid support collision
        if ctx60.support and (entry - float(ctx60.support)) < 0.4 * atr:
            continue

        if variant == "A":
            # Require recent 60m displacement then 15m retest reject (not chase).
            swing_high = max(c.high for c in hist60[-20:]) if len(hist60) >= 20 else None
            if swing_high is None:
                continue
            disp = (float(swing_high) - entry) / atr
            if disp < float(params.get("min_disp_atr", 1.2)):
                continue
            # Retest: price traded up toward SMA/structure then rejected
            lb = int(params.get("retest_lookback_15m", 10))
            window = hist15[-lb:]
            if len(window) < 5:
                continue
            touched = any(c.high >= float(ctx60.sma20) * 0.998 for c in window[:-1])
            if not touched:
                continue
            # No chase: last bar not already extended far below SMA
            if (float(ctx60.sma20) - entry) / atr > float(params.get("max_chase_atr", 0.35)) + disp * 0.15:
                # allow moderate; reject only extreme chase below
                if (float(ctx60.sma20) - entry) / atr > float(params.get("max_chase_atr", 0.35)) * 4:
                    continue
            # Reject if last 3 bars are runaway breakdown without retest shape
            if all(c.close < c.open for c in hist15[-3:]) and hist15[-1].low < hist15[-3].low:
                if (hist15[-3].high - hist15[-1].low) / atr > 1.5:
                    continue
            ok = True
            meta["disp_atr"] = disp

        elif variant == "B":
            if stop_atr > float(params.get("max_stop_atr", 1.1)):
                continue
            # Late entry: already extended below swing high too far
            swing_high = max(c.high for c in hist60[-16:]) if len(hist60) >= 16 else None
            if swing_high is None:
                continue
            ext = (float(swing_high) - entry) / atr
            if ext > float(params.get("max_extension_atr", 1.0)):
                continue
            # Must still be below SMA (continuation)
            if entry > float(ctx60.sma20) * 1.002:
                continue
            # RR after cost proxy
            gross_rr = target_atr / stop_atr if stop_atr > 0 else 0
            if gross_rr < float(params.get("min_rr_after_cost_proxy", 1.5)):
                continue
            ok = True
            meta["extension_atr"] = ext
            meta["gross_rr"] = gross_rr

        elif variant == "C":
            swing_high = max(c.high for c in hist60[-20:]) if len(hist60) >= 20 else None
            if swing_high is None:
                continue
            disp = (float(swing_high) - entry) / atr
            if disp < float(params.get("min_disp_atr", 1.0)):
                continue
            ch = oi_change_pct(oi_pts, ts)
            if ch is None:
                continue  # MISSING blocks
            # OI collapsing hard against short continuation → block
            if ch < float(params.get("oi_collapse_max_pct", -0.02)):
                continue
            fr = lookup_asof(fund_pts, ts, "funding_rate")
            if fr is None:
                continue  # MISSING blocks
            if abs(float(fr)) > float(params.get("funding_abs_max", 0.0008)):
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
            min_move_to_cost=float(params.get("min_move_to_cost", 2.8)),
        )
        if not econ_ok:
            continue

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
            strategy=f"trend_following:{variant}",
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


def _symbol_concentration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    filled = [r for r in rows if r.get("net_pnl") is not None]
    if not filled:
        return {"max_share": 0.0, "by_symbol": {}}
    c = Counter(str(r.get("symbol") or "?") for r in filled)
    n = len(filled)
    by = {k: v / n for k, v in c.items()}
    return {"max_share": max(by.values()) if by else 0.0, "by_symbol": by}


def _fold_concentration(fold_summaries: list[dict[str, Any]]) -> float:
    pnls = [float(f.get("net_pnl") or 0) for f in fold_summaries]
    pos = [p for p in pnls if p > 0]
    if not pos:
        return 0.0
    return max(pos) / sum(pos) if sum(pos) > 0 else 0.0


def classify_h4(
    *,
    replay: dict[str, Any],
    adv: dict[str, Any],
    fold_ok: int,
    fold_usable: int,
    symbol_max_share: float,
    fold_profit_share: float,
    data_valid: bool,
) -> str:
    if not data_valid:
        return "DATA_INVALID"
    n = int(replay.get("completed_trade_count") or 0)
    if n < H4_GATES["min_completed_trades"]:
        return "INSUFFICIENT_SAMPLE"
    gexp = replay.get("gross_expectancy")
    nexp = replay.get("net_expectancy") or replay.get("expectancy")
    npf = replay.get("net_profit_factor") or replay.get("profit_factor")
    apf = adv.get("net_profit_factor") or adv.get("profit_factor")
    mdd = replay.get("maximum_drawdown")
    if gexp is None or float(gexp) <= 0:
        return "REJECTED_NO_GROSS_EDGE"
    if nexp is None or float(nexp) <= 0 or npf is None or float(npf) < 1:
        return "REJECTED_COST_DOMINATED"
    if float(npf) < float(H4_GATES["min_base_profit_factor"]):
        return "REJECTED_COST_DOMINATED"
    if apf is None or float(apf) < float(H4_GATES["min_adverse_profit_factor"]):
        return "REJECTED_COST_DOMINATED"
    if fold_usable < int(H4_GATES["min_walk_forward_folds"]) or fold_ok < 2:
        return "REJECTED_UNSTABLE_ACROSS_FOLDS"
    if symbol_max_share > float(H4_GATES["max_symbol_share"]):
        return "REJECTED_CONCENTRATED_EDGE"
    if fold_profit_share > float(H4_GATES["max_fold_profit_share"]):
        return "REJECTED_CONCENTRATED_EDGE"
    if mdd is not None and abs(float(mdd)) > float(H4_GATES["max_drawdown_abs"]):
        return "REJECTED_UNSTABLE_ACROSS_FOLDS"
    # Replay validated intermediate, then WF
    if fold_ok >= 2 and float(npf) >= float(H4_GATES["min_base_profit_factor"]) and float(apf) >= float(
        H4_GATES["min_adverse_profit_factor"]
    ):
        return "WALK_FORWARD_VALIDATED"
    return "REPLAY_VALIDATED"


def run_edge_research_h4(
    *,
    datasets_15: list[MarketDataset],
    datasets_60: list[MarketDataset],
    datasets_240: list[MarketDataset],
    micro: dict[str, Any],
    prereg_checksum: str,
) -> dict[str, Any]:
    assert prereg_checksum == preregistration_checksum(), "H4_PREREGISTRATION_CHECKSUM_MISMATCH"
    by60 = {d.symbol: d for d in datasets_60}
    by240 = {d.symbol: d for d in datasets_240}
    results = []

    for hyp in HYPOTHESES_H4:
        hid = hyp["hypothesis_id"]
        print(f"h4 building {hid}", flush=True)
        pairs: list[tuple[Any, list[Candle]]] = []
        gate_total = gate_pass = 0
        for ds in datasets_15:
            built = build_h4_candidates(
                hyp,
                ds15=ds,
                ds60=by60.get(ds.symbol),
                ds240=by240.get(ds.symbol),
                micro=micro,
                stride=16,
            )
            by_ts = {c.ts_ms: i for i, c in enumerate(ds.candles)}
            for cand, _meta in built:
                gate_total += 1
                geo = evaluate_structural_geometry(cand.evidence)
                if geo.get("cost_gate_pass"):
                    gate_pass += 1
                idx = by_ts.get(cand.candidate_snapshot_time)
                if idx is None:
                    continue
                pairs.append((cand, ds.candles[idx + 1 :]))
        pairs.sort(key=lambda x: x[0].candidate_snapshot_time)
        print(f"h4 sim {hid} pairs={len(pairs)} gate_pass={gate_pass}/{gate_total}", flush=True)

        base_rows = _simulate(pairs, apply_costs=True, cost_mode="BASE_CONSERVATIVE")
        gross_rows = _simulate(pairs, apply_costs=False, cost_mode="GROSS_NO_COST_DIAGNOSTIC")
        adv_rows = _simulate(pairs, apply_costs=True, cost_mode="ADVERSE_COST_STRESS")
        base_s = _summ_rows(base_rows)
        gross_s = _summ_rows(gross_rows)
        adv_s = _summ_rows(adv_rows)
        if base_s.get("gross_expectancy") is None and gross_s.get("expectancy") is not None:
            base_s["gross_expectancy"] = gross_s.get("gross_expectancy") or gross_s.get("expectancy")
        if base_s.get("gross_profit_factor") is None:
            base_s["gross_profit_factor"] = gross_s.get("gross_profit_factor") or gross_s.get("profit_factor")

        m = len(base_rows)
        cuts = [0, m // 3, 2 * m // 3, m]
        fold_ok = fold_usable = 0
        folds = []
        fold_summaries = []
        for fi in range(3):
            a, b = cuts[fi], cuts[fi + 1]
            fs = _summ_rows(base_rows[a:b])
            folds.append({"fold": f"outer_{fi+1}", "summary": fs, "pair_count": b - a})
            fold_summaries.append(fs)
            cn = int(fs.get("completed_trade_count") or 0)
            if cn >= MIN_SAMPLE_FOLD:
                fold_usable += 1
                pf = fs.get("net_profit_factor") or fs.get("profit_factor")
                exp = fs.get("net_expectancy") or fs.get("expectancy")
                if pf is not None and float(pf) > 1 and exp is not None and float(exp) > 0:
                    fold_ok += 1

        sym = _symbol_concentration(base_rows)
        fold_share = _fold_concentration(fold_summaries)
        status = classify_h4(
            replay=base_s,
            adv=adv_s,
            fold_ok=fold_ok,
            fold_usable=fold_usable,
            symbol_max_share=float(sym["max_share"]),
            fold_profit_share=fold_share,
            data_valid=True,
        )
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
                "cost_gate_pass_rate": (gate_pass / gate_total) if gate_total else None,
                "completed_trade_count": base_s.get("completed_trade_count"),
                "fold_count": 3,
                "fold_ok": fold_ok,
                "fold_usable": fold_usable,
                "gross_expectancy": base_s.get("gross_expectancy") or gross_s.get("expectancy"),
                "net_expectancy": base_s.get("net_expectancy") or base_s.get("expectancy"),
                "profit_factor": base_s.get("net_profit_factor") or base_s.get("profit_factor"),
                "adverse_profit_factor": adv_s.get("net_profit_factor") or adv_s.get("profit_factor"),
                "win_rate": base_s.get("win_rate"),
                "maximum_drawdown": base_s.get("maximum_drawdown"),
                "maximum_consecutive_losses": base_s.get("consecutive_losses"),
                "symbol_concentration": sym,
                "fold_concentration": fold_share,
                "lookahead_violation_count": int(base_s.get("look_ahead_contamination") or 0),
                "risk_limit_breach_count": int(base_s.get("risk_limit_breach_count") or 0),
                "liquidation_incident_count": int(base_s.get("liquidation_incident_count") or 0),
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
        "schema": "h4_edge_research_v1_summary",
        "preregistration_checksum": prereg_checksum,
        "gates": H4_GATES,
        "hypothesis_results": results,
        "selected_h4_primary_policy": primary["hypothesis_id"] if primary else None,
        "selected_primary_result": primary,
        "walk_forward_validated_count": len(validated),
    }
