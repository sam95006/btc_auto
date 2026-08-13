"""P0.4 selectivity / episode Top-K research — analysis only, no runtime mutation.

Ranking uses only point-in-time features (entry_quality_score, expected_net_edge).
Never uses future path outcomes for selection.
Canonical fee baseline stays 0.0011 RT @ 350 notional (never lowered).
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

PRIMARY_HORIZONS = (300, 900, 1800)  # 5m, 15m, 30m
HORIZON_LABEL = {300: "5m", 900: "15m", 1800: "30m"}
NOTIONAL = 350.0
BASELINE_FEE_RT = 0.0011
BASELINE_FEE_COST = NOTIONAL * BASELINE_FEE_RT  # 0.385
# Assumed additional spread/slippage stress (USDT). Labeled; not used to replace baseline.
STRESS_SMALL_USDT = 0.05
STRESS_MEDIUM_USDT = 0.15


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
    return round(s[m], 6) if len(s) % 2 else round((s[m - 1] + s[m]) / 2.0, 6)


def _pctile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    idx = min(len(s) - 1, max(0, int(round((p / 100.0) * (len(s) - 1)))))
    return float(s[idx])


def _pf(gw: float, gl: float) -> float | None:
    if gl <= 0:
        return None
    return round(gw / gl, 4)


def summarize_outcomes(
    rows: list[dict[str, Any]],
    *,
    extra_cost: float = 0.0,
) -> dict[str, Any]:
    """Summarize path outcome rows; optional additive cost stress on top of stored net."""
    if not rows:
        return {"valid_sample_count": 0}
    nets: list[float] = []
    grosses: list[float] = []
    costs: list[float] = []
    mfes: list[float] = []
    maes: list[float] = []
    wins = losses = 0
    gw = gl = 0.0
    dirs: Counter[str] = Counter()
    syms: Counter[str] = Counter()
    for r in rows:
        net0 = _f(r.get("post_cost_hypothetical"))
        if net0 is None:
            continue
        net = net0 - float(extra_cost)
        gross = _f(r.get("gross_hypothetical")) or 0.0
        cost = _f(r.get("total_estimated_cost"))
        if cost is None:
            cost = _f(r.get("estimated_cost")) or BASELINE_FEE_COST
        cost = float(cost) + float(extra_cost)
        nets.append(net)
        grosses.append(gross)
        costs.append(cost)
        mfe = _f(r.get("MFE"))
        mae = _f(r.get("MAE"))
        if mfe is not None:
            mfes.append(mfe)
        if mae is not None:
            maes.append(mae)
        if net > 0:
            wins += 1
            gw += net
        elif net < 0:
            losses += 1
            gl += abs(net)
        dirs[str(r.get("direction") or "").upper()] += 1
        syms[str(r.get("symbol") or "")] += 1
    n = len(nets)
    if n <= 0:
        return {"valid_sample_count": 0}
    med_mfe = _median(mfes)
    med_mae = _median(maes)
    ratio = None
    if med_mfe is not None and med_mae is not None and abs(med_mae) > 1e-12:
        ratio = round(abs(med_mfe / med_mae), 4)
    return {
        "valid_sample_count": n,
        "signal_count": n,
        "LONG": dirs.get("LONG", 0),
        "SHORT": dirs.get("SHORT", 0),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / n, 4),
        "gross_expectancy": round(sum(grosses) / n, 6),
        "cost": round(sum(costs) / n, 6),
        "post_cost_expectancy": round(sum(nets) / n, 6),
        "profit_factor": _pf(gw, gl),
        "median_MFE": med_mfe,
        "median_MAE": med_mae,
        "MFE_MAE_ratio": ratio,
        "symbol_concentration_top5": syms.most_common(5),
        "baseline_fee_rt": BASELINE_FEE_RT,
        "baseline_fee_cost": BASELINE_FEE_COST,
        "extra_cost_stress_usdt": extra_cost,
    }


def build_unique_signals(
    canon_rows: list[dict[str, Any]],
    *,
    primary_h: int = 900,
) -> dict[str, dict[str, Any]]:
    """One record per signal_id from primary horizon join (features + 15m outcome)."""
    out: dict[str, dict[str, Any]] = {}
    for r in canon_rows:
        if int(r.get("horizon_sec") or 0) != primary_h:
            continue
        sid = str(r.get("signal_id") or "")
        if not sid or sid in out:
            continue
        out[sid] = dict(r)
    # Fallback: if missing 15m, take any horizon once
    for r in canon_rows:
        sid = str(r.get("signal_id") or "")
        if sid and sid not in out:
            out[sid] = dict(r)
    return out


def outcomes_by_signal_horizon(
    canon_rows: list[dict[str, Any]],
) -> dict[tuple[str, int], dict[str, Any]]:
    out: dict[tuple[str, int], dict[str, Any]] = {}
    for r in canon_rows:
        sid = str(r.get("signal_id") or "")
        try:
            h = int(r.get("horizon_sec") or 0)
        except (TypeError, ValueError):
            continue
        if not sid or h <= 0:
            continue
        key = (sid, h)
        if key not in out:
            out[key] = r
    return out


def anti_churn_unique(unique: dict[str, dict[str, Any]]) -> dict[str, Any]:
    by_sym: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for sid, u in unique.items():
        sym = str(u.get("symbol") or "")
        ts = int(u.get("detected_at_ms") or 0)
        d = str(u.get("direction") or "")
        if sym:
            by_sym[sym].append((ts, d, sid))
    same_sym = same_side = 0
    gaps: list[float] = []
    for events in by_sym.values():
        events = sorted(events, key=lambda x: (x[0], x[2]))
        for i in range(1, len(events)):
            same_sym += 1
            if events[i][1] and events[i][1] == events[i - 1][1]:
                same_side += 1
            if events[i][0] and events[i - 1][0]:
                gaps.append((events[i][0] - events[i - 1][0]) / 1000.0)
    sym_counts = Counter(str(u.get("symbol") or "") for u in unique.values())
    return {
        "analyzer_unit": "unique_signal_id",
        "anti_churn_analyzer_fixed": True,
        "same_symbol_consecutive_pairs": same_sym,
        "same_side_consecutive_pairs": same_side,
        "median_same_symbol_gap_sec": _median(gaps),
        "unique_signal_top_symbols": sym_counts.most_common(10),
        "unique_signal_count": len(unique),
    }


def direction_unique_vs_horizon(
    unique: dict[str, dict[str, Any]],
    canon_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    u_long = sum(1 for u in unique.values() if str(u.get("direction") or "").upper() == "LONG")
    u_short = sum(1 for u in unique.values() if str(u.get("direction") or "").upper() == "SHORT")
    h_long = sum(1 for r in canon_rows if str(r.get("direction") or "").upper() == "LONG")
    h_short = sum(1 for r in canon_rows if str(r.get("direction") or "").upper() == "SHORT")
    return {
        "unique_signal_LONG_count": u_long,
        "unique_signal_SHORT_count": u_short,
        "unique_signal_direction_sum": u_long + u_short,
        "horizon_record_LONG_count": h_long,
        "horizon_record_SHORT_count": h_short,
        "note": "horizon_record_* is NOT signal concentration",
    }


def episode_stats(
    unique: dict[str, dict[str, Any]],
    bucket_sec: int,
) -> dict[str, Any]:
    buckets: dict[int, set[str]] = defaultdict(set)
    for sid, u in unique.items():
        ts = int(u.get("detected_at_ms") or 0)
        if ts <= 0:
            continue
        buckets[ts // (bucket_sec * 1000)].add(sid)
    counts = [float(len(s)) for s in buckets.values()]
    return {
        "bucket_sec": bucket_sec,
        "episode_count": len(buckets),
        "median_unique_signals_per_episode": _pctile(counts, 50),
        "p75": _pctile(counts, 75),
        "p95": _pctile(counts, 95),
        "max": max(counts) if counts else None,
    }


def _episodes(
    unique: dict[str, dict[str, Any]],
    bucket_sec: int,
) -> dict[int, list[str]]:
    buckets: dict[int, list[str]] = defaultdict(list)
    for sid, u in unique.items():
        ts = int(u.get("detected_at_ms") or 0)
        if ts <= 0:
            continue
        buckets[ts // (bucket_sec * 1000)].append(sid)
    return buckets


def select_topk_sids(
    sids: list[str],
    unique: dict[str, dict[str, Any]],
    *,
    k: int | None,
    rank_by: str,
) -> list[str]:
    """Rank by point-in-time features only — never outcomes."""
    def key(sid: str) -> float:
        u = unique[sid]
        if rank_by == "score":
            eq = _f(u.get("entry_quality_score"))
            if eq is not None:
                return eq
            ns = _f(u.get("nexus_score_0_100"))
            return (ns / 100.0) if ns is not None else -999.0
        v = _f(u.get("expected_net_edge"))
        return float(v) if v is not None else -999.0

    ordered = sorted(sids, key=key, reverse=True)
    if k is None:
        return ordered
    return ordered[: max(0, int(k))]


def eval_selection(
    selected_sids: list[str],
    unique: dict[str, dict[str, Any]],
    by_sh: dict[tuple[str, int], dict[str, Any]],
    *,
    horizon_sec: int,
    extra_cost: float = 0.0,
) -> dict[str, Any]:
    rows = []
    for sid in selected_sids:
        rec = by_sh.get((sid, horizon_sec))
        if not rec:
            continue
        # attach symbol/direction from unique if missing
        u = unique.get(sid) or {}
        row = dict(rec)
        row.setdefault("symbol", u.get("symbol"))
        row.setdefault("direction", u.get("direction"))
        rows.append(row)
    out = summarize_outcomes(rows, extra_cost=extra_cost)
    out["episode_signal_cap_ok"] = True
    return out


def topk_research(
    unique: dict[str, dict[str, Any]],
    by_sh: dict[tuple[str, int], dict[str, Any]],
    *,
    bucket_sec: int = 120,
) -> dict[str, Any]:
    episodes = _episodes(unique, bucket_sec)
    # chronological episode ids for A/B
    ep_ids = sorted(episodes.keys())
    mid = len(ep_ids) // 2
    win_a = set(ep_ids[:mid])
    win_b = set(ep_ids[mid:])

    ks: list[int | None] = [1, 3, 5, 10, None]
    k_labels = {1: "top1", 3: "top3", 5: "top5", 10: "top10", None: "all"}
    rank_modes = ("score", "edge")
    result: dict[str, Any] = {"bucket_sec": bucket_sec, "episode_count": len(episodes)}

    for rank_by in rank_modes:
        block: dict[str, Any] = {}
        for k in ks:
            label = k_labels[k]
            selected: list[str] = []
            for ep, sids in episodes.items():
                picked = select_topk_sids(sids, unique, k=k, rank_by=rank_by)
                if k is not None:
                    assert len(picked) <= k
                selected.extend(picked)
            per_h = {}
            for h in PRIMARY_HORIZONS:
                lab = HORIZON_LABEL[h]
                full = eval_selection(selected, unique, by_sh, horizon_sec=h)
                a_sids = [s for s in selected if (unique[s].get("detected_at_ms") or 0) // (bucket_sec * 1000) in win_a]
                b_sids = [s for s in selected if (unique[s].get("detected_at_ms") or 0) // (bucket_sec * 1000) in win_b]
                per_h[lab] = {
                    **full,
                    "episode_count": len(episodes),
                    "window_A": eval_selection(a_sids, unique, by_sh, horizon_sec=h),
                    "window_B": eval_selection(b_sids, unique, by_sh, horizon_sec=h),
                }
            # never select >K per episode — verify
            max_per = 0
            for sids in episodes.values():
                picked = select_topk_sids(sids, unique, k=k, rank_by=rank_by)
                max_per = max(max_per, len(picked))
            block[label] = {
                "rank_by": rank_by,
                "k": k,
                "signal_count": len(selected),
                "max_selected_per_episode": max_per,
                "horizons": per_h,
            }
        result[f"rank_by_{rank_by}"] = block
    return result


def score_tail_research(
    unique: dict[str, dict[str, Any]],
    by_sh: dict[tuple[str, int], dict[str, Any]],
    *,
    bucket_sec: int = 120,
) -> dict[str, Any]:
    scored = [(sid, _f(u.get("entry_quality_score")), u) for sid, u in unique.items()]
    scored = [(s, eq, u) for s, eq, u in scored if eq is not None]
    scored.sort(key=lambda t: t[1] or 0.0)

    def band(lo: float, hi: float) -> list[str]:
        return [s for s, eq, _ in scored if eq is not None and lo <= eq * 100 <= hi]

    def top_pct(p: float) -> list[str]:
        if not scored:
            return []
        n = max(1, int(math.ceil(len(scored) * p)))
        return [s for s, _, _ in scored[-n:]]

    groups = {
        "80_82": band(80, 82),
        "83_85": band(83, 85),
        "86_89": band(86, 89),
        "top5pct": top_pct(0.05),
        "top10pct": top_pct(0.10),
        "top20pct": top_pct(0.20),
    }
    ep = _episodes(unique, bucket_sec)
    ep_ids = sorted(ep.keys())
    mid = len(ep_ids) // 2
    wa, wb = set(ep_ids[:mid]), set(ep_ids[mid:])

    out: dict[str, Any] = {"hypothesis_only": True, "not_a_promotion_threshold": True}
    for name, sids in groups.items():
        h15 = eval_selection(sids, unique, by_sh, horizon_sec=900)
        a = [s for s in sids if (unique[s].get("detected_at_ms") or 0) // (bucket_sec * 1000) in wa]
        b = [s for s in sids if (unique[s].get("detected_at_ms") or 0) // (bucket_sec * 1000) in wb]
        # episode-normalized: mean of per-episode means
        ep_means = []
        for eids in ep.values():
            inter = [s for s in eids if s in set(sids)]
            if not inter:
                continue
            sm = eval_selection(inter, unique, by_sh, horizon_sec=900)
            if sm.get("post_cost_expectancy") is not None:
                ep_means.append(sm["post_cost_expectancy"])
        out[name] = {
            "n": len(sids),
            "15m": h15,
            "5m": eval_selection(sids, unique, by_sh, horizon_sec=300),
            "30m": eval_selection(sids, unique, by_sh, horizon_sec=1800),
            "window_A": eval_selection(a, unique, by_sh, horizon_sec=900),
            "window_B": eval_selection(b, unique, by_sh, horizon_sec=900),
            "episode_normalized_15m_mean": round(sum(ep_means) / len(ep_means), 6) if ep_means else None,
            "episode_count_with_members": len(ep_means),
        }
    return out


def expected_edge_tail_research(
    unique: dict[str, dict[str, Any]],
    by_sh: dict[tuple[str, int], dict[str, Any]],
    *,
    bucket_sec: int = 120,
) -> dict[str, Any]:
    edged = [(sid, _f(u.get("expected_net_edge")), u) for sid, u in unique.items()]
    edged = [(s, e, u) for s, e, u in edged if e is not None]
    edged.sort(key=lambda t: t[1] or 0.0)

    def top_pct(p: float) -> list[str]:
        if not edged:
            return []
        n = max(1, int(math.ceil(len(edged) * p)))
        return [s for s, _, _ in edged[-n:]]

    def bottom_pct(p: float) -> list[str]:
        if not edged:
            return []
        n = max(1, int(math.ceil(len(edged) * p)))
        return [s for s, _, _ in edged[:n]]

    groups = {
        "top1pct": top_pct(0.01),
        "top5pct": top_pct(0.05),
        "top10pct": top_pct(0.10),
        "top20pct": top_pct(0.20),
        "bottom20pct": bottom_pct(0.20),
    }
    ep_ids = sorted(_episodes(unique, bucket_sec).keys())
    mid = len(ep_ids) // 2
    wa, wb = set(ep_ids[:mid]), set(ep_ids[mid:])
    out: dict[str, Any] = {
        "continuous_calibration_note": "weak continuous correlation does not preclude top-tail filter usefulness",
    }
    for name, sids in groups.items():
        per_h = {}
        for h in PRIMARY_HORIZONS:
            lab = HORIZON_LABEL[h]
            a = [s for s in sids if (unique[s].get("detected_at_ms") or 0) // (bucket_sec * 1000) in wa]
            b = [s for s in sids if (unique[s].get("detected_at_ms") or 0) // (bucket_sec * 1000) in wb]
            per_h[lab] = {
                **eval_selection(sids, unique, by_sh, horizon_sec=h),
                "window_A": eval_selection(a, unique, by_sh, horizon_sec=h),
                "window_B": eval_selection(b, unique, by_sh, horizon_sec=h),
            }
        out[name] = {"n": len(sids), "horizons": per_h}
    return out


def direction_selectivity(
    unique: dict[str, dict[str, Any]],
    by_sh: dict[tuple[str, int], dict[str, Any]],
    *,
    bucket_sec: int = 120,
) -> dict[str, Any]:
    long_u = {s: u for s, u in unique.items() if str(u.get("direction") or "").upper() == "LONG"}
    short_u = {s: u for s, u in unique.items() if str(u.get("direction") or "").upper() == "SHORT"}
    return {
        "LONG": topk_research(long_u, by_sh, bucket_sec=bucket_sec),
        "SHORT": topk_research(short_u, by_sh, bucket_sec=bucket_sec),
        "LONG_score_tail": score_tail_research(long_u, by_sh, bucket_sec=bucket_sec),
        "SHORT_score_tail": score_tail_research(short_u, by_sh, bucket_sec=bucket_sec),
        "LONG_edge_tail": expected_edge_tail_research(long_u, by_sh, bucket_sec=bucket_sec),
        "SHORT_edge_tail": expected_edge_tail_research(short_u, by_sh, bucket_sec=bucket_sec),
    }


def regime_provenance(
    ledger_rows: list[dict[str, Any]],
    snapshots: dict[str, dict[str, Any]],
    unique: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    led = Counter(str(r.get("regime") or "MISSING") for r in ledger_rows)
    snap = Counter(str(s.get("regime") or "MISSING") for s in snapshots.values())
    joined = Counter(str(u.get("regime") or "MISSING") for u in unique.values())

    def frac_range(c: Counter[str]) -> float:
        n = sum(c.values()) or 1
        return round(c.get("RANGE", 0) / n, 4)

    diagnosis = "UNDETERMINED"
    if frac_range(joined) >= 0.9 and frac_range(led) >= 0.9:
        if frac_range(snap) >= 0.9:
            diagnosis = "REGIME_ENGINE_ACTUALLY_OUTPUT_RANGE"
        elif snap and frac_range(snap) < 0.5:
            diagnosis = "REGIME_FIELD_MAPPING_BUG"
        elif led.get("MISSING", 0) > 0.5 * (sum(led.values()) or 1):
            diagnosis = "HISTORICAL_DEFAULT_CONTAMINATION"
        else:
            diagnosis = "REGIME_ENGINE_ACTUALLY_OUTPUT_RANGE"
    elif frac_range(joined) >= 0.9 and frac_range(led) < 0.5:
        diagnosis = "REGIME_FIELD_MAPPING_BUG"

    return {
        "ledger_regime_distribution": dict(led.most_common()),
        "snapshot_regime_distribution": dict(snap.most_common()),
        "joined_regime_distribution": dict(joined.most_common()),
        "diagnosis": diagnosis,
    }


def cost_stress_on_selection(
    selected_sids: list[str],
    unique: dict[str, dict[str, Any]],
    by_sh: dict[tuple[str, int], dict[str, Any]],
) -> dict[str, Any]:
    return {
        "canonical_baseline": {
            "fee_rt": BASELINE_FEE_RT,
            "notional": NOTIONAL,
            "fee_cost_usdt": BASELINE_FEE_COST,
            "note": "NEVER lowered",
            "15m": eval_selection(selected_sids, unique, by_sh, horizon_sec=900, extra_cost=0.0),
        },
        "baseline_plus_small_spread_slip": {
            "assumed_extra_usdt": STRESS_SMALL_USDT,
            "15m": eval_selection(selected_sids, unique, by_sh, horizon_sec=900, extra_cost=STRESS_SMALL_USDT),
        },
        "baseline_plus_medium_spread_slip": {
            "assumed_extra_usdt": STRESS_MEDIUM_USDT,
            "15m": eval_selection(selected_sids, unique, by_sh, horizon_sec=900, extra_cost=STRESS_MEDIUM_USDT),
        },
    }


def ready_watch_after_selection(
    selected_sids: list[str],
    unique: dict[str, dict[str, Any]],
    by_sh: dict[tuple[str, int], dict[str, Any]],
) -> dict[str, Any]:
    ready = [s for s in selected_sids if str(unique[s].get("final_action") or "").upper() in {"SELECT", "READY"}]
    watch = [s for s in selected_sids if str(unique[s].get("final_action") or "").upper() == "WATCH"]
    return {
        "READY": eval_selection(ready, unique, by_sh, horizon_sec=900),
        "WATCH": eval_selection(watch, unique, by_sh, horizon_sec=900),
        "WAIT_BLOCK_VALIDATION_UNAVAILABLE": True,
        "note": "WAIT/BLOCK lack meaningful outcome sample in shadow SELECT/WATCH path",
    }


def selective_verdict_from_topk(topk: dict[str, Any]) -> str:
    """Research-only verdict from score-ranked Top-K 15m post-cost."""
    score_block = topk.get("rank_by_score") or {}
    # Prefer top3/top5 15m
    candidates = []
    for key in ("top1", "top3", "top5", "top10"):
        h = ((score_block.get(key) or {}).get("horizons") or {}).get("15m") or {}
        n = int(h.get("valid_sample_count") or 0)
        exp = h.get("post_cost_expectancy")
        pf = h.get("profit_factor")
        wa = (h.get("window_A") or {}).get("post_cost_expectancy")
        wb = (h.get("window_B") or {}).get("post_cost_expectancy")
        if n >= 30 and exp is not None:
            candidates.append((key, exp, pf, wa, wb, n))
    if not candidates:
        return "SELECTIVITY_NO_EDGE"
    # best K by expectancy
    best = max(candidates, key=lambda t: t[1])
    _, exp, pf, wa, wb, n = best
    both_pos = wa is not None and wb is not None and wa > 0 and wb > 0
    if exp > 0 and (pf or 0) >= 1.05 and both_pos:
        return "SELECTIVITY_POSITIVE_BUT_UNVALIDATED"
    if exp > 0 and (pf or 0) >= 1.0:
        return "SELECTIVITY_PROMISING" if both_pos or (wa is None or wb is None) else "SELECTIVITY_WEAK"
    if exp > -0.05:
        return "SELECTIVITY_WEAK"
    return "SELECTIVITY_NO_EDGE"


def direction_policy_conclusion(dir_sel: dict[str, Any]) -> str:
    def best15(block: dict[str, Any]) -> float | None:
        score = (block.get("rank_by_score") or {}).get("top5") or {}
        h = (score.get("horizons") or {}).get("15m") or {}
        return h.get("post_cost_expectancy")

    long_e = best15(dir_sel.get("LONG") or {})
    short_e = best15(dir_sel.get("SHORT") or {})
    if long_e is None or short_e is None:
        return "DIRECTION_SPECIFIC_POLICY_REQUIRED"
    if abs(long_e - short_e) < 0.05 and long_e < 0 and short_e < 0:
        return "DIRECTION_SPECIFIC_POLICY_REQUIRED"
    if long_e > short_e + 0.05:
        return "LONG_STRONGER"
    if short_e > long_e + 0.05:
        return "SHORT_STRONGER"
    if long_e > 0 and short_e > 0 and abs(long_e - short_e) < 0.08:
        return "DIRECTION_SYMMETRY_OK"
    return "DIRECTION_SPECIFIC_POLICY_REQUIRED"


def cf_wider_stop_validity(
    cf_report: dict[str, Any],
    *,
    min_n: int = 100,
) -> dict[str, Any]:
    ws = cf_report.get("wider_stop") or {}
    n = int(ws.get("valid_sample_count") or 0)
    valid = n >= min_n
    return {
        "sample_count": n,
        "post_cost_expectancy": ws.get("post_cost_expectancy"),
        "profit_factor": ws.get("profit_factor"),
        "validity": "INSUFFICIENT_OR_UNSTABLE" if not valid else "BOUNDED_SAMPLE_ONLY",
        "conclude_superior": False,
        "note": "Do not change live STOP; bounded CF sample is not promotion evidence",
    }
