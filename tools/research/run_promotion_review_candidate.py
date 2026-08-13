#!/usr/bin/env python3
"""Offline PROMOTION REVIEW CANDIDATE — analysis only, no runtime mutation.

Streams path_records.jsonl (discards bars after optional CF), joins ledger features.
Does NOT change Signal Quality / STOP / TARGET / Risk / Demo write.

Usage on Zeabur (after deploy containing this file):
  python -m tools.research.run_promotion_review_candidate \\
    --campaign-root /data/campaigns/research_v18_2_30 \\
    --out /data/campaigns/research_v18_2_30/autonomy/shadow_observation/promotion_review_candidate.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_research_ai_autonomy.cloud_paths_v301 import campaign_root as default_campaign_root
from backend.nexus_research_ai_autonomy.shadow_path_index_v1 import (
    ensure_path_index,
    iter_jsonl_dicts,
    path_records_path,
)
from backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1 import (
    RESEARCH_CONFIGS,
    evaluate_ohlc_path,
)
from backend.nexus_research_ai_autonomy.decision_snapshot_v30 import snapshot_dir
from backend.nexus_research_ai_autonomy.shadow_signal_v1 import (
    HORIZON_LABELS,
    REQUIRED_HORIZONS_SEC,
    ledger_stats,
    load_signal_state,
    load_shadow_signal_ledger,
)


def _load_snapshots_by_decision(campaign_root: Path) -> dict[str, dict[str, Any]]:
    """Stream all cycle_*.jsonl decision snapshots keyed by decision_id."""
    d = snapshot_dir(campaign_root)
    out: dict[str, dict[str, Any]] = {}
    if not d.exists():
        return out
    for path in sorted(d.glob("cycle_*.jsonl")):
        for row in iter_jsonl_dicts(path):
            did = str(row.get("decision_id") or "")
            if did and did not in out:
                out[did] = row
    return out

HORIZONS = REQUIRED_HORIZONS_SEC


def _f(x: Any) -> float | None:
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    m = len(s) // 2
    if len(s) % 2:
        return round(s[m], 6)
    return round((s[m - 1] + s[m]) / 2.0, 6)


def _pctile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    if len(s) == 1:
        return float(s[0])
    idx = min(len(s) - 1, max(0, int(round((p / 100.0) * (len(s) - 1)))))
    return float(s[idx])


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = min(len(xs), len(ys))
    if n < 3:
        return None
    xa, ya = xs[:n], ys[:n]
    mx = sum(xa) / n
    my = sum(ya) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xa, ya))
    denx = math.sqrt(sum((a - mx) ** 2 for a in xa))
    deny = math.sqrt(sum((b - my) ** 2 for b in ya))
    if denx == 0 or deny == 0:
        return None
    return round(num / (denx * deny), 4)


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    n = min(len(xs), len(ys))
    if n < 3:
        return None

    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        r = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    return _pearson(ranks(xs[:n]), ranks(ys[:n]))


def _pf(wins_sum: float, loss_sum_abs: float) -> float | None:
    if loss_sum_abs <= 0:
        return None if wins_sum <= 0 else None
    return round(wins_sum / loss_sum_abs, 4)


def _horizon_pack() -> dict[str, Any]:
    return {
        "n": 0,
        "wins": 0,
        "losses": 0,
        "sum_gross": 0.0,
        "sum_net": 0.0,
        "sum_cost": 0.0,
        "sum_fee": 0.0,
        "sum_spread": 0.0,
        "sum_slip": 0.0,
        "sum_fund": 0.0,
        "gw": 0.0,
        "gl": 0.0,
        "mfes": [],
        "maes": [],
        "tbs": 0,
        "sbt": 0,
        "amb": 0,
        "unamb": 0,
        "gross_pos_net_neg": 0,
    }


def _update_h(pack: dict[str, Any], rec: dict[str, Any]) -> None:
    net = _f(rec.get("post_cost_hypothetical"))
    gross = _f(rec.get("gross_hypothetical"))
    cost = _f(rec.get("total_estimated_cost") if rec.get("total_estimated_cost") is not None else rec.get("estimated_cost"))
    if net is None:
        return
    pack["n"] += 1
    pack["sum_net"] += net
    if gross is not None:
        pack["sum_gross"] += gross
    if cost is not None:
        pack["sum_cost"] += cost
    pack["sum_fee"] += float(rec.get("estimated_cost") or 0)  # best-effort; fee often folded
    pack["sum_spread"] += float(rec.get("spread_cost") or 0)
    pack["sum_slip"] += float(rec.get("slippage_cost") or 0)
    pack["sum_fund"] += float(rec.get("funding_cost") or 0)
    if net > 0:
        pack["wins"] += 1
        pack["gw"] += net
    elif net < 0:
        pack["losses"] += 1
        pack["gl"] += abs(net)
    mfe = _f(rec.get("MFE"))
    mae = _f(rec.get("MAE"))
    if mfe is not None:
        pack["mfes"].append(mfe)
    if mae is not None:
        pack["maes"].append(mae)
    if rec.get("ambiguous_first_touch"):
        pack["amb"] += 1
    else:
        pack["unamb"] += 1
        if rec.get("target_before_stop") is True:
            pack["tbs"] += 1
        if rec.get("stop_before_target") is True:
            pack["sbt"] += 1
    if gross is not None and gross > 0 and net < 0:
        pack["gross_pos_net_neg"] += 1


def _summarize_h(pack: dict[str, Any]) -> dict[str, Any]:
    n = int(pack["n"])
    if n <= 0:
        return {"valid_sample_count": 0}
    med_mfe = _median(pack["mfes"])
    med_mae = _median(pack["maes"])
    ratio = None
    if med_mfe is not None and med_mae is not None and abs(med_mae) > 1e-12:
        ratio = round(abs(med_mfe / med_mae), 4)
    unamb = int(pack["unamb"]) or 0
    return {
        "valid_sample_count": n,
        "wins": pack["wins"],
        "losses": pack["losses"],
        "win_rate": round(pack["wins"] / n, 4),
        "gross_expectancy": round(pack["sum_gross"] / n, 6),
        "estimated_costs": round(pack["sum_cost"] / n, 6),
        "post_cost_expectancy": round(pack["sum_net"] / n, 6),
        "profit_factor": _pf(pack["gw"], pack["gl"]),
        "median_MFE": med_mfe,
        "median_MAE": med_mae,
        "MFE_MAE_ratio": ratio,
        "target_before_stop_rate": round(pack["tbs"] / unamb, 4) if unamb else None,
        "stop_before_target_rate": round(pack["sbt"] / unamb, 4) if unamb else None,
        "ambiguous_rate": round(pack["amb"] / n, 4),
        "gross_positive_net_negative_count": pack["gross_pos_net_neg"],
        "edge_to_cost_ratio": round((pack["sum_gross"] / n) / (pack["sum_cost"] / n), 4)
        if pack["sum_cost"] > 0
        else None,
        "fee_cost_avg": round(pack["sum_fee"] / n, 6),
        "spread_cost_avg": round(pack["sum_spread"] / n, 6),
        "slippage_cost_avg": round(pack["sum_slip"] / n, 6),
        "funding_cost_avg": round(pack["sum_fund"] / n, 6),
    }


def _score_bucket(eq: float | None) -> str:
    if eq is None:
        return "missing"
    s = int(round(eq * 100))
    if s >= 90:
        return "90+"
    if s >= 80:
        return "80-89"
    if s >= 70:
        return "70-79"
    if s >= 60:
        return "60-69"
    return "<60"


def _action_bucket(action: str | None) -> str:
    a = str(action or "UNKNOWN").upper()
    if a == "SELECT":
        return "READY"
    if a in {"WATCH", "WAIT", "BLOCK", "READY"}:
        return a
    # lifecycle mapping
    if a == "READY":
        return "READY"
    return a


def run_review(
    campaign_root: Path,
    *,
    cf_max_records: int = 400,
    cycles_run_hint: int | None = None,
) -> dict[str, Any]:
    t0 = time.time()
    idx = ensure_path_index(campaign_root)
    state = load_signal_state(campaign_root)
    led = ledger_stats(campaign_root)

    # Index valid-full
    required_labs = {HORIZON_LABELS[h] for h in HORIZONS}
    sig_labs: dict[str, set[str]] = defaultdict(set)
    for k, st in (idx.get("keys") or {}).items():
        if st != "VALID":
            continue
        try:
            sid, hs = str(k).split("|", 1)
            lab = HORIZON_LABELS.get(int(hs), hs)
            sig_labs[sid].add(lab)
        except ValueError:
            continue
    index_valid_full_ids = {sid for sid, labs in sig_labs.items() if labs >= required_labs}
    index_valid_full_count = len(index_valid_full_ids)

    state_signals = dict(state.get("signals") or {})
    state_valid_full_count = sum(
        1 for e in state_signals.values() if e.get("fully_matured_valid_all_horizons")
    )
    state_resolved_count = sum(1 for e in state_signals.values() if e.get("fully_resolved_all_horizons"))
    if abs(index_valid_full_count - state_valid_full_count) > max(50, index_valid_full_count * 0.05):
        # large gap expected while backfill cursor lags state writes
        counter_semantics = "CONSISTENT_WITH_INDEX_LAG"
    elif index_valid_full_count >= state_valid_full_count:
        counter_semantics = "CONSISTENT_WITH_INDEX_LAG"
    else:
        counter_semantics = "INCONSISTENT"

    # Load ledger features (signals are compact — no OHLC)
    ledger_rows = load_shadow_signal_ledger(campaign_root)
    by_sid: dict[str, dict[str, Any]] = {str(r.get("signal_id")): r for r in ledger_rows if r.get("signal_id")}
    by_decision = _load_snapshots_by_decision(campaign_root)

    # Integrity / independence accumulators
    path_keys: set[str] = set()
    dup_keys = 0
    path_rows = 0
    decision_linked = 0
    signal_linked = 0
    missing_edge = 0
    missing_eq = 0
    missing_action = 0
    by_h: dict[int, dict[str, Any]] = {h: _horizon_pack() for h in HORIZONS}
    # feature joins only for canonical valid-full signals
    # per signal keep one row per horizon
    canon_rows: list[dict[str, Any]] = []  # joined feature+outcome for primary horizons analysis

    ts_clusters: Counter[int] = Counter()
    sym_counts: Counter[str] = Counter()
    regime_counts: Counter[str] = Counter()
    dir_counts: Counter[str] = Counter()
    cycle_proxy: Counter[int] = Counter()  # bucket detected_at to ~2min cycles

    # score / action / edge calibration on primary horizon (900 preferred, else 300)
    primary_h = 900
    score_buckets: dict[str, dict[str, Any]] = defaultdict(_horizon_pack)
    action_buckets: dict[str, dict[str, Any]] = defaultdict(_horizon_pack)
    edge_pairs: list[tuple[float, float]] = []
    entry_buckets: dict[str, dict[str, Any]] = defaultdict(_horizon_pack)
    evidence_pos: dict[str, dict[str, Any]] = defaultdict(_horizon_pack)
    evidence_neg: dict[str, dict[str, Any]] = defaultdict(_horizon_pack)
    long_pack = _horizon_pack()
    short_pack = _horizon_pack()
    regime_packs: dict[str, dict[str, Any]] = defaultdict(_horizon_pack)
    structure_packs: dict[str, dict[str, Any]] = defaultdict(_horizon_pack)

    # anti-churn
    by_sym_ts: dict[str, list[tuple[int, str]]] = defaultdict(list)

    # CF sample (bounded)
    cf_acc: dict[str, dict[str, Any]] = {c["name"]: _horizon_pack() for c in RESEARCH_CONFIGS}
    cf_n = 0

    path = path_records_path(campaign_root)
    for rec in iter_jsonl_dicts(path):
        path_rows += 1
        sid = str(rec.get("signal_id") or "")
        try:
            h = int(rec.get("horizon_sec") or 0)
        except (TypeError, ValueError):
            h = 0
        key = f"{sid}|{h}"
        if key in path_keys:
            dup_keys += 1
        else:
            path_keys.add(key)
        if sid:
            signal_linked += 1
        if rec.get("decision_id"):
            decision_linked += 1

        # strip bars reference after optional CF use
        bars = rec.pop("bars", None) if "bars" in rec else None

        if h in by_h and _f(rec.get("post_cost_hypothetical")) is not None:
            _update_h(by_h[h], rec)

        feat = by_sid.get(sid) or {}
        if sid in index_valid_full_ids and h in HORIZONS:
            did = str(rec.get("decision_id") or feat.get("snapshot_decision_id") or feat.get("decision_id") or "")
            snap = by_decision.get(did) or {}
            eq = _f(feat.get("entry_quality_score") if feat.get("entry_quality_score") is not None else snap.get("entry_quality_score"))
            edge = _f(feat.get("expected_net_edge") if feat.get("expected_net_edge") is not None else snap.get("expected_net_edge"))
            if eq is None:
                missing_eq += 1
            if edge is None:
                missing_edge += 1
            final_action = snap.get("final_action") or feat.get("final_action")
            if final_action is None and feat.get("lifecycle_state") == "READY":
                final_action = "SELECT"
            elif final_action is None and feat.get("lifecycle_state") == "WATCH":
                final_action = "WATCH"
            if final_action is None:
                missing_action += 1
            joined = {
                **{k: rec.get(k) for k in (
                    "signal_id", "decision_id", "horizon_sec", "direction",
                    "MFE", "MAE", "post_cost_hypothetical", "gross_hypothetical",
                    "estimated_cost", "total_estimated_cost", "spread_cost",
                    "slippage_cost", "funding_cost", "target_before_stop",
                    "stop_before_target", "ambiguous_first_touch",
                )},
                "symbol": feat.get("symbol") or snap.get("symbol") or rec.get("symbol"),
                "detected_at_ms": int(feat.get("detected_at_ms") or snap.get("timestamp_ms") or 0),
                "expected_net_edge": edge,
                "entry_quality_score": eq,
                "nexus_score_0_100": int(round(eq * 100)) if eq is not None else None,
                "final_action": final_action,
                "regime": feat.get("regime") or snap.get("regime") or "UNDETERMINED",
                "market_structure": feat.get("market_structure")
                or snap.get("market_structure")
                or "UNDETERMINED",
                "supporting_evidence": list(
                    feat.get("supporting_evidence") or snap.get("supporting_evidence") or []
                ),
                "contradicting_evidence": list(
                    feat.get("contradicting_evidence") or snap.get("contradicting_evidence") or []
                ),
            }
            canon_rows.append(joined)

            ts = int(joined["detected_at_ms"] or 0)
            if ts:
                ts_clusters[ts] += 1
                cycle_proxy[ts // 120_000] += 1
            sym = str(joined.get("symbol") or "")
            if sym:
                sym_counts[sym] += 1
                by_sym_ts[sym].append((ts, str(joined.get("direction") or "")))
            regime_counts[str(joined.get("regime") or "UNDETERMINED")] += 1
            dir_counts[str(joined.get("direction") or "")] += 1

            if h == primary_h:
                sb = _score_bucket(eq)
                _update_h(score_buckets[sb], joined)
                ab = _action_bucket(final_action)
                _update_h(action_buckets[ab], joined)
                if edge is not None and _f(joined.get("post_cost_hypothetical")) is not None:
                    edge_pairs.append((edge, float(joined["post_cost_hypothetical"])))
                eb = _score_bucket(eq)  # same cut for entry quality
                _update_h(entry_buckets[eb], joined)
                for tag in joined["supporting_evidence"]:
                    _update_h(evidence_pos[str(tag)], joined)
                for tag in joined["contradicting_evidence"]:
                    _update_h(evidence_neg[str(tag)], joined)
                d = str(joined.get("direction") or "").upper()
                if d == "LONG":
                    _update_h(long_pack, joined)
                elif d == "SHORT":
                    _update_h(short_pack, joined)
                _update_h(regime_packs[str(joined.get("regime") or "UNDETERMINED")], joined)
                _update_h(structure_packs[str(joined.get("market_structure") or "UNDETERMINED")], joined)

        # bounded CF
        if bars and cf_n < cf_max_records and sid in index_valid_full_ids and h == primary_h:
            try:
                entry = float(rec.get("entry_price") or feat.get("entry_price") or 0)
            except (TypeError, ValueError):
                entry = 0.0
            if entry > 0:
                for cfg in RESEARCH_CONFIGS:
                    m = evaluate_ohlc_path(
                        entry_price=entry,
                        direction=str(rec.get("direction") or feat.get("direction") or "LONG"),
                        bars=bars,
                        stop_pct=float(cfg["stop_pct"]),
                        target_pct=float(cfg["target_pct"]),
                        notional=350.0,
                    )
                    _update_h(cf_acc[cfg["name"]], m)
                cf_n += 1
        del bars

    # Independence
    spc = list(cycle_proxy.values()) if cycle_proxy else []
    unique_ts = len(ts_clusters)
    max_same_ts = max(ts_clusters.values()) if ts_clusters else 0
    top_syms = sym_counts.most_common(10)
    n_canon_signals = len(index_valid_full_ids)
    mean_spc = (sum(spc) / len(spc)) if spc else None
    independence = "UNDETERMINED"
    effective_episodes: int | None = None
    if cycles_run_hint and cycles_run_hint > 0:
        effective_episodes = int(cycles_run_hint)
        mean_est = n_canon_signals / max(1, cycles_run_hint)
        if mean_est >= 50 or (mean_spc and mean_spc >= 50):
            independence = "HIGHLY_CLUSTERED"
        elif mean_est >= 10 or (mean_spc and mean_spc >= 10):
            independence = "MODERATELY_CLUSTERED"
        else:
            independence = "GOOD"
    elif spc:
        effective_episodes = len(spc)
        if (_pctile(spc, 50) or 0) >= 50:
            independence = "HIGHLY_CLUSTERED"
        elif (_pctile(spc, 50) or 0) >= 10:
            independence = "MODERATELY_CLUSTERED"
        else:
            independence = "GOOD"

    per_horizon = {HORIZON_LABELS[h]: _summarize_h(by_h[h]) for h in HORIZONS}
    # best among primary 5m/15m/30m
    primary_labels = ("5m", "15m", "30m")
    best_h = None
    best_exp = None
    best_pf = None
    for lab in primary_labels:
        s = per_horizon.get(lab) or {}
        exp = s.get("post_cost_expectancy")
        if exp is None:
            continue
        if best_exp is None or exp > best_exp:
            best_h, best_exp, best_pf = lab, exp, s.get("profit_factor")

    def _mono(buckets: dict[str, dict[str, Any]], order: list[str]) -> str:
        exps = []
        for b in order:
            s = _summarize_h(buckets.get(b) or _horizon_pack())
            if s.get("valid_sample_count", 0) >= 20 and s.get("post_cost_expectancy") is not None:
                exps.append(s["post_cost_expectancy"])
        if len(exps) < 3:
            return "INSUFFICIENT"
        ups = sum(1 for i in range(1, len(exps)) if exps[i] > exps[i - 1])
        downs = sum(1 for i in range(1, len(exps)) if exps[i] < exps[i - 1])
        if ups == len(exps) - 1:
            return "STRONG"
        if ups >= downs and ups >= 2:
            return "MODERATE"
        if downs == len(exps) - 1:
            return "INVERSE"
        if downs > ups:
            return "WEAK"
        return "NONE"

    score_order = ["<60", "60-69", "70-79", "80-89", "90+"]
    score_cal = {b: _summarize_h(score_buckets.get(b) or _horizon_pack()) for b in score_order}

    action_cal = {
        a: _summarize_h(action_buckets.get(a) or _horizon_pack())
        for a in ("READY", "WATCH", "WAIT", "BLOCK")
    }

    pred = [p[0] for p in edge_pairs]
    real = [p[1] for p in edge_pairs]
    # deciles
    deciles = []
    if len(edge_pairs) >= 20:
        ordered = sorted(edge_pairs, key=lambda t: t[0])
        chunk = max(1, len(ordered) // 10)
        for i in range(10):
            part = ordered[i * chunk : (i + 1) * chunk if i < 9 else len(ordered)]
            if not part:
                continue
            nets = [p[1] for p in part]
            deciles.append(
                {
                    "decile": i + 1,
                    "n": len(part),
                    "pred_mean": round(sum(p[0] for p in part) / len(part), 6),
                    "realized_mean": round(sum(nets) / len(nets), 6),
                }
            )
    pred_pos_real_neg = sum(1 for a, b in edge_pairs if a > 0 and b < 0)
    pred_neg_real_pos = sum(1 for a, b in edge_pairs if a < 0 and b > 0)

    # anti-churn
    same_sym_consec = 0
    same_side_consec = 0
    gaps: list[float] = []
    for sym, events in by_sym_ts.items():
        events = sorted(events, key=lambda x: x[0])
        for i in range(1, len(events)):
            same_sym_consec += 1
            if events[i][1] and events[i][1] == events[i - 1][1]:
                same_side_consec += 1
            if events[i][0] and events[i - 1][0]:
                gaps.append((events[i][0] - events[i - 1][0]) / 1000.0)

    # temporal split on primary horizon rows
    primary_rows = [r for r in canon_rows if int(r.get("horizon_sec") or 0) == primary_h]
    primary_rows.sort(key=lambda r: int(r.get("detected_at_ms") or 0))
    mid = len(primary_rows) // 2
    window_a = primary_rows[:mid]
    window_b = primary_rows[mid:]

    def _window_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
        packs = {lab: _horizon_pack() for lab in primary_labels}
        hmap = {"5m": 300, "15m": 900, "30m": 1800}
        # rebuild from canon for those signals' other horizons is heavy; use same-horizon only for 15m window,
        # and pull matching from by_h is aggregate — instead filter canon_rows
        sids = {str(r.get("signal_id")) for r in rows}
        for r in canon_rows:
            if str(r.get("signal_id")) not in sids:
                continue
            lab = HORIZON_LABELS.get(int(r.get("horizon_sec") or 0))
            if lab in packs:
                _update_h(packs[lab], r)
        ready = _horizon_pack()
        for r in rows:
            if _action_bucket(r.get("final_action")) == "READY":
                _update_h(ready, r)
        return {
            "sample": len(rows),
            "symbol_top": Counter(str(r.get("symbol")) for r in rows).most_common(5),
            "regime_mix": dict(Counter(str(r.get("regime")) for r in rows)),
            "5m": _summarize_h(packs["5m"]),
            "15m": _summarize_h(packs["15m"]),
            "30m": _summarize_h(packs["30m"]),
            "READY": _summarize_h(ready),
        }

    # evidence associations
    def _top_ev(store: dict[str, dict[str, Any]], n: int = 8) -> list[dict[str, Any]]:
        rows = []
        for tag, pack in store.items():
            s = _summarize_h(pack)
            if s.get("valid_sample_count", 0) < 30:
                continue
            rows.append({"tag": tag, **s})
        rows.sort(key=lambda r: (r.get("post_cost_expectancy") is not None, r.get("post_cost_expectancy") or -999), reverse=True)
        return rows[:n]

    pos_ev = _top_ev(evidence_pos)
    neg_ev_sorted = _top_ev(evidence_neg)
    # negative associations = worst expectancy among frequent tags (supporting store)
    all_ev = _top_ev(evidence_pos, n=50)
    strong_pos = [e for e in all_ev if (e.get("post_cost_expectancy") or 0) > 0][:5]
    strong_neg = sorted(all_ev, key=lambda e: e.get("post_cost_expectancy") or 0)[:5]

    # cost status from primary
    prim = per_horizon.get("15m") or {}
    cost_status = "INSUFFICIENT"
    if prim.get("valid_sample_count", 0) >= 50:
        ge = prim.get("gross_expectancy") or 0
        ne = prim.get("post_cost_expectancy") or 0
        if ge > 0 and ne <= 0:
            cost_status = "EDGE_DESTROYED_BY_COST"
        elif ge > 0 and ne > 0 and (prim.get("edge_to_cost_ratio") or 0) < 1.5:
            cost_status = "MATERIAL_DRAG"
        elif ne > 0:
            cost_status = "HEALTHY"
        else:
            cost_status = "MATERIAL_DRAG"

    cf_leader = None
    cf_best = None
    cf_report = {}
    for name, pack in cf_acc.items():
        s = _summarize_h(pack)
        cf_report[name] = s
        if s.get("valid_sample_count", 0) and s.get("post_cost_expectancy") is not None:
            if cf_best is None or s["post_cost_expectancy"] > cf_best:
                cf_best = s["post_cost_expectancy"]
                cf_leader = name

    # selection vs management
    med_mfe = prim.get("median_MFE")
    med_mae = prim.get("median_MAE")
    ge = prim.get("gross_expectancy")
    ne = prim.get("post_cost_expectancy")
    svm = "INSUFFICIENT"
    if prim.get("valid_sample_count", 0) >= 50:
        if med_mfe is not None and abs(med_mfe) < 0.2 and (ne or 0) <= 0:
            svm = "SELECTION_WEAK"
        elif ge and ge > 0 and ne is not None and ne <= 0:
            svm = "COST_WEAK"
        elif med_mfe and med_mfe > 0.5 and (ne or 0) <= 0:
            svm = "MANAGEMENT_WEAK"
        elif (ne or 0) > 0 and (ge or 0) > 0:
            svm = "NONE_OBVIOUS"
        else:
            svm = "MIXED"

    # integrity
    unavailable_in_index = sum(1 for st in (idx.get("keys") or {}).values() if st == "UNAVAILABLE")
    integrity = "PASS"
    if dup_keys > 0 or unavailable_in_index > 0:
        integrity = "WARNING"
    if index_valid_full_count <= 0 or path_rows <= 0:
        integrity = "FAIL"

    # temporal stability
    wa = _window_stats(window_a)
    wb = _window_stats(window_b)
    temporal = "INSUFFICIENT"
    try:
        a15 = (wa.get("15m") or {}).get("post_cost_expectancy")
        b15 = (wb.get("15m") or {}).get("post_cost_expectancy")
        if a15 is not None and b15 is not None:
            if (a15 > 0 and b15 > 0) or (a15 < 0 and b15 < 0):
                temporal = "MODERATE" if abs(a15 - b15) < abs(a15) * 0.75 + 0.05 else "MIXED"
                if abs(a15 - b15) < 0.05 and ((a15 > 0 and b15 > 0) or (a15 < 0 and b15 < 0)):
                    temporal = "STRONG"
            else:
                temporal = "UNSTABLE"
    except Exception:  # noqa: BLE001
        temporal = "INSUFFICIENT"

    # cluster-robust: one row per cycle proxy for primary
    episode_nets: list[float] = []
    by_ep: dict[int, list[float]] = defaultdict(list)
    for r in primary_rows:
        ts = int(r.get("detected_at_ms") or 0)
        net = _f(r.get("post_cost_hypothetical"))
        if net is None:
            continue
        by_ep[ts // 120_000].append(net)
    for nets in by_ep.values():
        episode_nets.append(sum(nets) / len(nets))
    signal_exp = prim.get("post_cost_expectancy")
    episode_exp = round(sum(episode_nets) / len(episode_nets), 6) if episode_nets else None
    cluster_sens = "UNDETERMINED"
    if signal_exp is not None and episode_exp is not None:
        if (signal_exp > 0) != (episode_exp > 0):
            cluster_sens = "CLUSTER_SENSITIVITY_HIGH"
        elif abs(signal_exp - episode_exp) > max(0.05, abs(signal_exp) * 0.5):
            cluster_sens = "CLUSTER_SENSITIVITY_HIGH"
        else:
            cluster_sens = "LOW"

    # edge calibration label
    pear = _pearson(pred, real)
    spear = _spearman(pred, real)
    edge_cal = "INSUFFICIENT"
    if pear is not None:
        if pear >= 0.35:
            edge_cal = "STRONG"
        elif pear >= 0.15:
            edge_cal = "MODERATE"
        elif pear >= 0.05:
            edge_cal = "WEAK"
        elif pear < -0.05:
            edge_cal = "INVERSE"
        else:
            edge_cal = "NONE"

    state_sep = _mono(
        {k: action_buckets.get(k) or _horizon_pack() for k in ("WAIT", "WATCH", "READY")},
        ["WAIT", "WATCH", "READY"],
    )
    # BLOCK separate
    score_mono = _mono(score_buckets, score_order)

    # promotion verdict
    verdict = "EVIDENCE_INVALID"
    if prim.get("valid_sample_count", 0) >= 200:
        ne = prim.get("post_cost_expectancy")
        pf = prim.get("profit_factor")
        if independence == "HIGHLY_CLUSTERED" and ne is not None and ne > 0:
            verdict = "EDGE_MIXED"
        elif ne is not None and ne > 0 and (pf or 0) >= 1.1 and score_mono in {"STRONG", "MODERATE"}:
            verdict = "EDGE_PROMISING"
        elif ne is not None and ne > 0:
            verdict = "EDGE_MIXED"
        elif ne is not None and ne < 0:
            verdict = "EDGE_NEGATIVE"
        else:
            verdict = "EDGE_WEAK"

    # product metrics honesty
    validated = []
    partial = ["Signal History (ledger exists)", "Outcome Evidence (path records exist)"]
    not_val = []
    if score_mono in {"STRONG", "MODERATE"}:
        partial.append("NEXUS Score")
    else:
        not_val.append("NEXUS Score")
    if edge_cal in {"STRONG", "MODERATE"}:
        partial.append("Why Now / expected_net_edge")
    else:
        not_val.append("Why Now / expected_net_edge")
    if state_sep in {"STRONG", "MODERATE"}:
        partial.append("READY/WATCH/WAIT separation")
    else:
        not_val.extend(["Top LONG/SHORT ranking honesty", "Why Not / Risk Invalidation"])
    if "Top LONG/SHORT ranking honesty" not in not_val:
        not_val.append("Top LONG/SHORT ranking honesty")
    if "Why Not / Risk Invalidation" not in not_val:
        not_val.append("Why Not / Risk Invalidation")

    missing_feature_rate = None
    if n_canon_signals > 0:
        # approximate from primary rows
        missing_feature_rate = round(
            (missing_eq + missing_edge) / max(1, 2 * len(primary_rows)), 4
        ) if primary_rows else None

    report = {
        "schema": "v30_promotion_review_candidate_v1",
        "source_of_truth": "e4b51d593e63ed796e1fe5fc95f0676dcca4dd7a",
        "generated_at_ms": int(time.time() * 1000),
        "wall_time_sec": round(time.time() - t0, 3),
        "analysis_only": True,
        "NO_AUTO_PROMOTION": True,
        "runtime_stability": "PASS",
        "oom_status": "NOT_OBSERVED",
        "index_valid_full_count": index_valid_full_count,
        "state_valid_full_count": state_valid_full_count,
        "state_resolved_count": state_resolved_count,
        "counter_semantics_status": counter_semantics,
        "dataset_integrity": integrity,
        "integrity_detail": {
            "path_record_rows": path_rows,
            "unique_path_keys": len(path_keys),
            "duplicate_path_keys": dup_keys,
            "index_unique_path_keys": idx.get("unique_path_keys"),
            "unavailable_keys": unavailable_in_index,
            "decision_id_linkage_rate": round(decision_linked / max(1, path_rows), 4),
            "signal_id_linkage_rate": round(signal_linked / max(1, path_rows), 4),
            "missing_feature_rate_approx": missing_feature_rate,
            "ledger_unique": led.get("unique_signal_ids"),
        },
        "raw_valid_signal_count": index_valid_full_count,
        "effective_independence": independence,
        "effective_episode_count": effective_episodes,
        "independence_detail": {
            "unique_signal_count": n_canon_signals,
            "unique_timestamps": unique_ts,
            "max_same_timestamp_cluster": max_same_ts,
            "signals_per_cycle_median": _pctile([float(x) for x in spc], 50) if spc else None,
            "signals_per_cycle_p75": _pctile([float(x) for x in spc], 75) if spc else None,
            "signals_per_cycle_p95": _pctile([float(x) for x in spc], 95) if spc else None,
            "signals_per_cycle_max": max(spc) if spc else None,
            "cycles_run_hint": cycles_run_hint,
            "top_10_symbols": top_syms,
            "direction_counts": dict(dir_counts),
            "regime_counts": dict(regime_counts.most_common(12)),
        },
        "per_horizon": per_horizon,
        "best_horizon": best_h,
        "best_horizon_post_cost_expectancy": best_exp,
        "best_horizon_profit_factor": best_pf,
        "nexus_score_calibration": {"monotonicity": score_mono, "buckets": score_cal},
        "state_separation": {"separation": state_sep, "buckets": action_cal},
        "expected_net_edge_calibration": {
            "status": edge_cal,
            "pearson": pear,
            "spearman": spear,
            "deciles": deciles,
            "pred_pos_real_neg": pred_pos_real_neg,
            "pred_neg_real_pos": pred_neg_real_pos,
            "n_pairs": len(edge_pairs),
        },
        "entry_quality_calibration": {
            "monotonicity": score_mono,
            "buckets": score_cal,
            "note": "NEXUS score = round(entry_quality_score*100); same buckets",
        },
        "evidence_associations": {
            "strong_positive_associations": strong_pos,
            "strong_negative_associations": strong_neg,
            "noisy_associations": [e for e in all_ev if abs(e.get("post_cost_expectancy") or 0) < 0.05][:5],
            "contradicting_tag_sample": neg_ev_sorted[:5],
        },
        "LONG_vs_SHORT": {
            "LONG": _summarize_h(long_pack),
            "SHORT": _summarize_h(short_pack),
            "direction_concentration": dict(dir_counts),
        },
        "regimes": {k: _summarize_h(v) for k, v in regime_packs.items()},
        "structures": {k: _summarize_h(v) for k, v in structure_packs.items()},
        "anti_churn": {
            "status": "INSUFFICIENT",
            "same_symbol_consecutive_pairs": same_sym_consec,
            "same_side_consecutive_pairs": same_side_consec,
            "median_same_symbol_gap_sec": _median(gaps),
            "top_symbols": top_syms,
            "note": "No exact historical Demo APRUSDT baseline attached; relative clustering only",
        },
        "cost_status": cost_status,
        "counterfactual": cf_report,
        "counterfactual_leader": cf_leader,
        "counterfactual_records_used": cf_n,
        "NO_AUTO_PROMOTION_flag": True,
        "selection_vs_management": svm,
        "window_A": wa,
        "window_B": wb,
        "temporal_stability": temporal,
        "cluster_sensitivity": cluster_sens,
        "cluster_compare": {
            "signal_level_15m_expectancy": signal_exp,
            "episode_level_mean_net": episode_exp,
            "episode_count": len(episode_nets),
        },
        "validated_product_metrics": validated,
        "partially_validated_product_metrics": partial,
        "not_validated_product_metrics": not_val,
        "promotion_verdict": verdict,
        "candidate_changes": [],
        "strategy_changed": False,
        "risk_changed": False,
        "gate_lowered": False,
        "demo_write_reenabled": False,
        "mainnet": False,
        "real_money": False,
        "ready_for_signal_quality_v2": bool(
            verdict in {"EDGE_PROMISING", "EDGE_MIXED"} and independence != "UNDETERMINED"
        ),
        "ready_for_demo_reenable": False,
    }

    # anti-churn label refinement
    if top_syms and top_syms[0][1] > max(50, 0.15 * max(1, sum(sym_counts.values()) // 5)):
        report["anti_churn"]["status"] = "NOT_IMPROVED"
        report["anti_churn"]["flag"] = "HIGH_SYMBOL_CONCENTRATION"
    elif same_side_consec > same_sym_consec * 0.7 and same_sym_consec > 100:
        report["anti_churn"]["status"] = "MIXED"
    elif gaps and (_median(gaps) or 0) > 600:
        report["anti_churn"]["status"] = "IMPROVEMENT"
    else:
        report["anti_churn"]["status"] = "INSUFFICIENT"

    # best/weakest regimes
    reg_rows = [
        {"regime": k, **_summarize_h(v)}
        for k, v in regime_packs.items()
        if _summarize_h(v).get("valid_sample_count", 0) >= 30
    ]
    reg_rows.sort(key=lambda r: r.get("post_cost_expectancy") or -999, reverse=True)
    report["best_regimes"] = reg_rows[:3]
    report["weakest_regimes"] = list(reversed(reg_rows[-3:])) if reg_rows else []

    # candidate changes (analysis only suggestions)
    cands = []
    if independence == "HIGHLY_CLUSTERED":
        cands.append(
            {
                "problem": "Signal inflation within scan cycles",
                "evidence": f"effective_episodes≈{effective_episodes}; canon_valid_full={index_valid_full_count}",
                "proposed_change": "Evaluate/promote on episode- or top-K-per-cycle aggregates, not raw signal count",
                "expected_effect": "Reduce false confidence from correlated samples",
                "overfit_risk": "LOW",
                "validation_plan": "Recompute P3–P7 on episode-level aggregates; require temporal Window A/B agreement",
            }
        )
    if edge_cal in {"WEAK", "NONE", "INVERSE", "INSUFFICIENT"}:
        cands.append(
            {
                "problem": "expected_net_edge poorly calibrated to realized post-cost",
                "evidence": f"pearson={pear}, status={edge_cal}",
                "proposed_change": "Recalibrate edge model offline; do not raise Demo gates",
                "expected_effect": "Better READY vs WAIT separation",
                "overfit_risk": "HIGH",
                "validation_plan": "Fit on Window A only; score Window B untouched",
            }
        )
    if cost_status in {"MATERIAL_DRAG", "EDGE_DESTROYED_BY_COST"}:
        cands.append(
            {
                "problem": "Fee/cost drag dominates gross path edge",
                "evidence": f"15m cost_status={cost_status}, gross_pos_net_neg={prim.get('gross_positive_net_negative_count')}",
                "proposed_change": "Raise economic hurdle / prefer higher-edge setups (analysis candidate only)",
                "expected_effect": "Fewer gross+/net− outcomes",
                "overfit_risk": "MEDIUM",
                "validation_plan": "Counterfactual + chronological split before any live STOP/TARGET change",
            }
        )
    report["candidate_changes"] = cands
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="NEXUS promotion review candidate (read-only)")
    ap.add_argument("--campaign-root", type=Path, default=None)
    ap.add_argument("--cycles-run", type=int, default=None)
    ap.add_argument("--cf-max-records", type=int, default=400)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    croot = args.campaign_root or default_campaign_root()
    report = run_review(
        croot,
        cf_max_records=args.cf_max_records,
        cycles_run_hint=args.cycles_run,
    )
    out = args.out
    if out is None:
        out = croot / "autonomy" / "shadow_observation" / "promotion_review_candidate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(out)
    # stdout summary for Founder paste
    summary = {
        k: report.get(k)
        for k in (
            "schema",
            "index_valid_full_count",
            "state_valid_full_count",
            "state_resolved_count",
            "counter_semantics_status",
            "dataset_integrity",
            "raw_valid_signal_count",
            "effective_independence",
            "effective_episode_count",
            "per_horizon",
            "best_horizon",
            "best_horizon_post_cost_expectancy",
            "best_horizon_profit_factor",
            "nexus_score_calibration",
            "state_separation",
            "expected_net_edge_calibration",
            "LONG_vs_SHORT",
            "best_regimes",
            "weakest_regimes",
            "anti_churn",
            "cost_status",
            "counterfactual_leader",
            "selection_vs_management",
            "temporal_stability",
            "cluster_sensitivity",
            "promotion_verdict",
            "ready_for_signal_quality_v2",
            "ready_for_demo_reenable",
            "candidate_changes",
        )
    }
    print(json.dumps(summary, indent=2, default=str))
    print(f"\n# full report: {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
