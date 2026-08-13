"""Read-only shadow observation gate — aggregate / validate / report only.

Does NOT change Signal Quality, ranking, STOP/TARGET/TRAIL, anti-churn, or Demo write.
Staged review thresholds (50 / 100 / 200) are diagnostic only — never auto-promote.
"""
from __future__ import annotations

import json
import math
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_research_ai_autonomy.decision_snapshot_v30 import load_latest_snapshots, snapshot_dir
from backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1 import (
    RESEARCH_CONFIGS,
    evaluate_ohlc_path,
    load_path_records,
    path_outcome_audit,
    path_records_for_counterfactual,
)
from backend.nexus_research_ai_autonomy.shadow_signal_v1 import (
    ledger_stats,
    load_shadow_signal_ledger,
    load_signal_state,
    shadow_dir,
)

OBSERVATION_SCHEMA = "v30_shadow_observation_v1"
HORIZONS = (60, 180, 300, 900, 1800)
HORIZON_LABELS = {60: "1m", 180: "3m", 300: "5m", 900: "15m", 1800: "30m"}

# Review thresholds only — not statistical significance, not Demo re-enable.
STAGE_THRESHOLDS = (
    ("EARLY_DIAGNOSTIC", 50),
    ("INTERMEDIATE_REVIEW", 100),
    ("PROMOTION_REVIEW_CANDIDATE", 200),
)


def observation_dir(campaign_root: Path) -> Path:
    return campaign_root / "autonomy" / "shadow_observation"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _median(vals: list[float]) -> float | None:
    return round(statistics.median(vals), 6) if vals else None


def _mean(vals: list[float]) -> float | None:
    return round(sum(vals) / len(vals), 6) if vals else None


def _pf(nets: list[float]) -> float | None:
    gw = sum(n for n in nets if n > 0)
    gl = abs(sum(n for n in nets if n < 0))
    return round(gw / gl, 4) if gl > 0 else None


def _bucket_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "sample_count": 0,
            "post_cost_expectancy": None,
            "profit_factor": None,
            "median_MFE": None,
            "median_MAE": None,
            "wins": 0,
            "losses": 0,
            "win_rate": None,
        }
    nets = [_f(r.get("post_cost_hypothetical")) for r in rows]
    nets_f = [n for n in nets if n is not None]
    mfes = [_f(r.get("MFE")) for r in rows]
    maes = [_f(r.get("MAE")) for r in rows]
    wins = sum(1 for n in nets_f if n > 0)
    losses = sum(1 for n in nets_f if n < 0)
    return {
        "sample_count": len(rows),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(nets_f), 4) if nets_f else None,
        "post_cost_expectancy": _mean(nets_f),
        "profit_factor": _pf(nets_f),
        "median_MFE": _median([m for m in mfes if m is not None]),
        "median_MAE": _median([m for m in maes if m is not None]),
    }


def _load_signals(campaign_root: Path) -> list[dict[str, Any]]:
    """Cumulative unique origin signals from immutable ledger (not latest-cycle overwrite)."""
    return load_shadow_signal_ledger(campaign_root)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _file_freshness(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "mtime": None, "updating": False}
    mtime = path.stat().st_mtime
    age_sec = time.time() - mtime
    return {
        "exists": True,
        "mtime_utc": datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "age_sec": round(age_sec, 1),
        # Heuristic: touched within last 30 minutes suggests alive updates
        "updating": age_sec < 1800,
    }


def _score_bucket(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 90:
        return "90+"
    if score >= 80:
        return "80-89"
    if score >= 70:
        return "70-79"
    if score >= 60:
        return "60-69"
    return "<60"


def _horizon_block(records: list[dict[str, Any]], *, horizon_sec: int) -> dict[str, Any]:
    rows = [r for r in records if int(r.get("horizon_sec") or 0) == horizon_sec]
    nets = [_f(r.get("post_cost_hypothetical")) for r in rows]
    nets_f = [n for n in nets if n is not None]
    grosses = [_f(r.get("gross_hypothetical")) for r in rows]
    gross_f = [g for g in grosses if g is not None]
    costs = [_f(r.get("total_estimated_cost") or r.get("estimated_cost")) for r in rows]
    cost_f = [c for c in costs if c is not None]
    mfes = [m for m in (_f(r.get("MFE")) for r in rows) if m is not None]
    maes = [m for m in (_f(r.get("MAE")) for r in rows) if m is not None]
    unamb = [r for r in rows if not r.get("ambiguous_first_touch")]
    tbs = sum(1 for r in unamb if r.get("target_before_stop") is True)
    sbt = sum(1 for r in unamb if r.get("stop_before_target") is True)
    amb = sum(1 for r in rows if r.get("ambiguous_first_touch"))
    wins = sum(1 for n in nets_f if n > 0)
    losses = sum(1 for n in nets_f if n < 0)
    symbols = Counter(str(r.get("symbol") or "") for r in rows)
    edge_ratios = [abs(g) / c for g, c in zip(gross_f, cost_f) if c and c > 0]
    med_mfe = _median(mfes)
    med_mae = _median(maes)
    mfe_mae_ratio = None
    if med_mfe is not None and med_mae is not None and med_mae != 0:
        mfe_mae_ratio = round(abs(med_mfe) / abs(med_mae), 4)
    return {
        "horizon_sec": horizon_sec,
        "horizon_label": HORIZON_LABELS.get(horizon_sec, str(horizon_sec)),
        "signals_matured": len(rows),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(nets_f), 4) if nets_f else None,
        "target_before_stop": tbs,
        "stop_before_target": sbt,
        "ambiguous_first_touch": amb,
        "target_before_stop_rate": round(tbs / len(unamb), 4) if unamb else None,
        "stop_before_target_rate": round(sbt / len(unamb), 4) if unamb else None,
        "ambiguous_rate": round(amb / len(rows), 4) if rows else None,
        "gross_expectancy": _mean(gross_f),
        "estimated_cost": round(sum(cost_f), 6) if cost_f else None,
        "post_cost_expectancy": _mean(nets_f),
        "profit_factor": _pf(nets_f),
        "median_MFE": med_mfe,
        "median_MAE": med_mae,
        "MFE_to_MAE_ratio": mfe_mae_ratio,
        "edge_to_cost_ratio": _median(edge_ratios),
        "symbol_concentration": dict(symbols.most_common(8)),
    }


def _join_signal_outcomes(
    signals: list[dict[str, Any]],
    records: list[dict[str, Any]],
    *,
    preferred_horizon: int = 900,
) -> list[dict[str, Any]]:
    """Join signals to one preferred-horizon outcome when available (else longest matured)."""
    by_sig: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        sid = str(r.get("signal_id") or "")
        if sid:
            by_sig[sid].append(r)
    joined: list[dict[str, Any]] = []
    for s in signals:
        sid = str(s.get("signal_id") or "")
        outs = by_sig.get(sid) or []
        pick = None
        for r in outs:
            if int(r.get("horizon_sec") or 0) == preferred_horizon:
                pick = r
                break
        if pick is None and outs:
            pick = sorted(outs, key=lambda x: int(x.get("horizon_sec") or 0))[-1]
        row = {
            **s,
            "nexus_score_0_100": int(round(float(s.get("entry_quality_score") or 0) * 100)),
            "post_cost_hypothetical": (pick or {}).get("post_cost_hypothetical"),
            "MFE": (pick or {}).get("MFE"),
            "MAE": (pick or {}).get("MAE"),
            "horizon_sec": (pick or {}).get("horizon_sec"),
            "ambiguous_first_touch": (pick or {}).get("ambiguous_first_touch"),
            "target_before_stop": (pick or {}).get("target_before_stop"),
            "measurement_quality": (pick or {}).get("measurement_quality"),
            "data_quality_warnings": (pick or {}).get("data_quality_warnings"),
            "expected_net_edge": s.get("expected_net_edge"),
            "has_outcome": pick is not None,
        }
        joined.append(row)
    return joined


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 5 or len(xs) != len(ys):
        return None

    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        r = [0.0] * len(vals)
        for rank, i in enumerate(order):
            r[i] = float(rank)
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    denx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    deny = math.sqrt(sum((b - my) ** 2 for b in ry))
    if denx == 0 or deny == 0:
        return None
    return round(num / (denx * deny), 4)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 5 or len(xs) != len(ys):
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    denx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    deny = math.sqrt(sum((b - my) ** 2 for b in ys))
    if denx == 0 or deny == 0:
        return None
    return round(num / (denx * deny), 4)


def _backfill_progress_fields(bf: dict[str, Any]) -> dict[str, Any]:
    return {
        "horizons_processed_this_cycle": bf.get("horizons_processed_this_cycle"),
        "pending_signals_before": bf.get("pending_signals_before"),
        "pending_signals_after": bf.get("pending_signals_after"),
        "state_synced_from_existing_paths": bf.get("state_synced_from_existing_paths"),
        "wall_time_sec": bf.get("wall_time_sec"),
        "cursor_index": bf.get("cursor_index"),
        "backfill_work_budget": bf.get("backfill_work_budget"),
        "backfill_time_budget": bf.get("backfill_time_budget"),
        "v2_priority_pending_before": bf.get("v2_priority_pending_before"),
        "v2_priority_processed_this_cycle": bf.get("v2_priority_processed_this_cycle"),
        "v2_priority_valid_written": bf.get("v2_priority_valid_written"),
        "v2_priority_unavailable_written": bf.get("v2_priority_unavailable_written"),
        "v2_priority_pending_after": bf.get("v2_priority_pending_after"),
        "legacy_processed_this_cycle": bf.get("legacy_processed_this_cycle"),
        "priority_starvation_prevented": bf.get("priority_starvation_prevented"),
    }


def build_observation_report_lightweight(
    *,
    campaign_root: Path,
    runtime_commit: str | None = None,
    backfill_status: str | None = None,
    backfill_progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Hot-cycle observation from compact index/state — NO full path_records OHLC load."""
    from backend.nexus_research_ai_autonomy.shadow_path_index_v1 import compact_observation_counters

    d = observation_dir(campaign_root)
    d.mkdir(parents=True, exist_ok=True)
    led = ledger_stats(campaign_root)
    state = load_signal_state(campaign_root)
    counters = compact_observation_counters(campaign_root, ledger_stats=led, state=state)
    gate = int(counters.get("signals_fully_matured_valid_all_horizons") or 0)
    if gate < 50:
        stage = "COLLECTING"
        next_ck = "EARLY_DIAGNOSTIC_AT_50_VALID_FULLY_MATURED"
    elif gate < 100:
        stage = "EARLY_DIAGNOSTIC_READY"
        next_ck = "INTERMEDIATE_REVIEW_AT_100_VALID_FULLY_MATURED"
    elif gate < 200:
        stage = "INTERMEDIATE_REVIEW_READY"
        next_ck = "PROMOTION_REVIEW_CANDIDATE_AT_200_VALID_FULLY_MATURED"
    else:
        stage = "PROMOTION_REVIEW_CANDIDATE"
        next_ck = "PROMOTION_REVIEW_CANDIDATE_REACHED"
    bf = backfill_progress or {}
    report = {
        "schema": OBSERVATION_SCHEMA,
        "mode": "lightweight_hot_cycle",
        "generated_at": _utc(),
        "runtime_commit": runtime_commit,
        "write_enabled": False,
        "demo_write_reenabled": False,
        "ready_for_demo_reenable": False,
        "strategy_changed": False,
        "risk_changed": False,
        "gate_lowered": False,
        "mainnet": False,
        "real_money": False,
        **counters,
        "signals_created": counters.get("unique_signals_created_total"),
        "signals_matured": gate,
        "signals_matured_1m": counters.get("signals_matured_valid_1m"),
        "signals_matured_3m": counters.get("signals_matured_valid_3m"),
        "signals_matured_5m": counters.get("signals_matured_valid_5m"),
        "signals_matured_15m": counters.get("signals_matured_valid_15m"),
        "signals_matured_30m": counters.get("signals_matured_valid_30m"),
        "backfill_status": backfill_status or bf.get("backfill_status"),
        "backfill_progress": _backfill_progress_fields(bf),
        "observation_stage": stage,
        "next_checkpoint": next_ck,
        "review_thresholds": {name: thr for name, thr in STAGE_THRESHOLDS},
        "heavy_analysis_deferred": True,
        "path_record_rows_note": "NOT_a_unique_signal_count",
    }
    latest = d / "observation_latest.json"
    tmp = latest.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(latest)
    return report


def build_observation_report(
    *,
    campaign_root: Path,
    runtime_commit: str | None = None,
    cycles_observed: int | None = None,
    backfill_status: str | None = None,
    backfill_progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full read-only observation aggregate — no strategy mutation."""
    d = observation_dir(campaign_root)
    d.mkdir(parents=True, exist_ok=True)

    signals = _load_signals(campaign_root)
    records = load_path_records(campaign_root)
    snapshots = load_latest_snapshots(campaign_root)
    outcomes = _load_jsonl(shadow_dir(campaign_root) / "shadow_outcomes.jsonl")
    thesis_path = campaign_root / "autonomy" / "thesis_state.json"
    led_stats = ledger_stats(campaign_root)
    audit = path_outcome_audit(campaign_root)
    state = load_signal_state(campaign_root)
    state_signals = dict(state.get("signals") or {})

    # Canonical maturity — VALID only for promotion gates
    unique_created = int(led_stats["unique_signal_ids"])
    matured_valid_by_h: dict[str, set[str]] = {HORIZON_LABELS[h]: set() for h in HORIZONS}
    matured_any_valid: set[str] = set()
    unavailable_count = 0
    for r in records:
        sid = str(r.get("signal_id") or "")
        if not sid:
            continue
        try:
            h = int(r.get("horizon_sec") or 0)
        except (TypeError, ValueError):
            continue
        label = HORIZON_LABELS.get(h)
        unavail = (
            r.get("unavailable_reason") == "HISTORICAL_PATH_UNAVAILABLE"
            or r.get("measurement_quality") == "HISTORICAL_PATH_UNAVAILABLE"
        )
        if unavail:
            unavailable_count += 1
            continue
        if label and (r.get("post_cost_hypothetical") is not None or r.get("bars")):
            matured_valid_by_h[label].add(sid)
            matured_any_valid.add(sid)

    fully_resolved = sum(1 for e in state_signals.values() if e.get("fully_resolved_all_horizons"))
    fully_valid = sum(1 for e in state_signals.values() if e.get("fully_matured_valid_all_horizons"))
    with_unavail = sum(1 for e in state_signals.values() if e.get("has_unavailable_horizon"))
    invalid_promo = sum(1 for e in state_signals.values() if e.get("invalid_for_promotion"))
    # Derive valid-full from path keys when state lagging
    if fully_valid == 0 and matured_any_valid:
        for sid in {str(s.get("signal_id") or "") for s in signals}:
            if sid and all(sid in matured_valid_by_h[HORIZON_LABELS[h]] for h in HORIZONS):
                fully_valid += 1
    pending = max(0, unique_created - fully_resolved)
    gate_matured = fully_valid
    matured_by_horizon = {k: len(v) for k, v in matured_valid_by_h.items()}

    # File update probes
    files = {
        "decision_snapshots": _file_freshness(snapshot_dir(campaign_root) / "latest_cycle_snapshots.json"),
        "shadow_signals": _file_freshness(shadow_dir(campaign_root) / "active_shadow_signals.jsonl"),
        "shadow_signals_latest_convenience": _file_freshness(
            shadow_dir(campaign_root) / "active_shadow_signals_latest.json"
        ),
        "path_records": _file_freshness(shadow_dir(campaign_root) / "path_records.jsonl"),
        "shadow_outcomes": _file_freshness(shadow_dir(campaign_root) / "shadow_outcomes.jsonl"),
        "shadow_quality": _file_freshness(shadow_dir(campaign_root) / "shadow_quality_latest.json"),
        "counterfactual": _file_freshness(shadow_dir(campaign_root) / "counterfactual_research_latest.json"),
        "shadow_signal_state": _file_freshness(shadow_dir(campaign_root) / "shadow_signal_state.json"),
        "shadow_backfill_progress": _file_freshness(
            shadow_dir(campaign_root) / "shadow_backfill_progress.json"
        ),
    }

    # O3 per-horizon (never merge into one headline win-rate)
    per_horizon = {HORIZON_LABELS[h]: _horizon_block(records, horizon_sec=h) for h in HORIZONS}

    # Action counts from latest snapshots
    action_counts = Counter(str(s.get("final_action") or "WAIT") for s in snapshots)
    state_map = {"SELECT": "READY", "WATCH": "WATCH", "WAIT": "WAIT", "BLOCK": "BLOCK"}
    state_counts = Counter(state_map.get(a, a) for a in action_counts.elements())

    joined = _join_signal_outcomes(signals, records)

    # O4 score / quality buckets
    by_score: dict[str, list] = defaultdict(list)
    by_eq: dict[str, list] = defaultdict(list)
    by_conf: dict[str, list] = defaultdict(list)
    by_edge: dict[str, list] = defaultdict(list)
    by_regime: dict[str, list] = defaultdict(list)
    by_structure: dict[str, list] = defaultdict(list)
    by_side: dict[str, list] = defaultdict(list)
    by_state: dict[str, list] = defaultdict(list)

    for row in joined:
        if not row.get("has_outcome"):
            continue
        by_score[_score_bucket(row.get("nexus_score_0_100"))].append(row)
        eq = _f(row.get("entry_quality_score"))
        by_eq[_score_bucket(int(round(eq * 100)) if eq is not None else None)].append(row)
        conf = _f(row.get("direction_confidence_quant"))
        by_conf[_score_bucket(int(round(conf * 100)) if conf is not None else None)].append(row)
        ene = _f(row.get("expected_net_edge"))
        if ene is None:
            by_edge["unknown"].append(row)
        elif ene >= 1.0:
            by_edge["edge>=1.0"].append(row)
        elif ene >= 0.0:
            by_edge["0<=edge<1.0"].append(row)
        else:
            by_edge["edge<0"].append(row)
        by_regime[str(row.get("regime") or (row.get("outcome") or {}).get("regime") or "UNDETERMINED")].append(row)
        # structure may live on snapshot join — use contradict/support as weak fallback
        by_structure[str(row.get("market_structure") or "UNDETERMINED")].append(row)
        by_side[str(row.get("direction") or "UNKNOWN").upper()].append(row)
        st = str(row.get("lifecycle_state") or "UNKNOWN")
        if st == "OUTCOME":
            # recover originating action from final_action if present
            fa = row.get("final_action")
            st = state_map.get(str(fa or ""), "OUTCOME")
        by_state[st].append(row)

    # Also bucket READY/WATCH from joined using originating snapshot action if stored
    for row in joined:
        if not row.get("has_outcome"):
            continue
        # shadow create maps SELECT→READY, WATCH→WATCH
        ls = str(row.get("lifecycle_state") or "")
        if ls in {"READY", "WATCH", "DETECTED", "OUTCOME"}:
            # Prefer signal creation state if still present before overwrite
            pass

    score_buckets = {k: _bucket_stats(v) for k, v in sorted(by_score.items())}
    # Calibration check: do higher scores have better expectancy?
    ordered = ["90+", "80-89", "70-79", "60-69", "<60"]
    expectancies = [
        (i, score_buckets[b]["post_cost_expectancy"])
        for i, b in enumerate(ordered)
        if b in score_buckets and score_buckets[b]["post_cost_expectancy"] is not None
    ]
    calibration = "INSUFFICIENT_SAMPLE"
    if len(expectancies) >= 3:
        # Weak monotonic check: higher score index smaller i should have higher expectancy
        xs = [e[0] for e in expectancies]
        ys = [float(e[1]) for e in expectancies]
        # invert score rank so higher score = lower index
        corr = _spearman([-x for x in xs], ys)
        if corr is None:
            calibration = "INSUFFICIENT_SAMPLE"
        elif corr >= 0.3:
            calibration = "POSITIVE_ASSOCIATION"
        elif corr <= -0.3:
            calibration = "WEAK_OR_INVERTED_CALIBRATION"
        else:
            calibration = "WEAK_CALIBRATION"

    # O5 READY vs WATCH — use creation lifecycle before OUTCOME overwrite when possible
    # Path: active signals that still say READY/WATCH, plus outcomes keyed by signal
    state_perf = {k: _bucket_stats(v) for k, v in by_state.items()}
    for row in joined:
        if not row.get("has_outcome"):
            continue
        # Infer from contradict evidence REPEATED → BLOCK path already in snapshots
    ready_watch = {
        "READY": state_perf.get("READY") or _bucket_stats([]),
        "WATCH": state_perf.get("WATCH") or _bucket_stats([]),
        "WAIT": state_perf.get("WAIT") or _bucket_stats([]),
        "BLOCK": state_perf.get("BLOCK") or _bucket_stats([]),
        "note": "OUTCOME lifecycle overwrites READY/WATCH on signal object; prefer snapshot final_action join when available",
    }
    # Better: from snapshots + path records via decision_id
    snap_by_dec = {str(s.get("decision_id")): s for s in snapshots if s.get("decision_id")}
    by_final: dict[str, list] = defaultdict(list)
    for r in records:
        # Prefer 15m for state comparison when present
        if int(r.get("horizon_sec") or 0) not in {300, 900, 1800}:
            continue
        dec = str(r.get("decision_id") or "")
        snap = snap_by_dec.get(dec)
        if not snap:
            continue
        st = state_map.get(str(snap.get("final_action") or "WAIT"), "WAIT")
        by_final[st].append(r)
    ready_watch["by_snapshot_final_action"] = {k: _bucket_stats(v) for k, v in by_final.items()}

    # O6 evidence tag associations
    evidence_assoc: dict[str, Any] = {}
    tag_rows: dict[str, list] = defaultdict(list)
    for row in joined:
        if not row.get("has_outcome"):
            continue
        for tag in list(row.get("supporting_evidence") or []) + list(row.get("contradicting_evidence") or []):
            tag_rows[str(tag)].append(row)
    for tag, rows in sorted(tag_rows.items(), key=lambda kv: -len(kv[1])):
        evidence_assoc[tag] = {
            "occurrence_count": len(rows),
            **_bucket_stats(rows),
            "association_only": True,
            "causal_claim": False,
        }

    # O7 anti-churn
    sig_sorted = sorted(
        [s for s in signals if s.get("detected_at_ms")],
        key=lambda s: int(s.get("detected_at_ms") or 0),
    )
    same_sym = same_side = 0
    for i in range(1, len(sig_sorted)):
        a, b = sig_sorted[i - 1], sig_sorted[i]
        if a.get("symbol") == b.get("symbol"):
            same_sym += 1
            if str(a.get("direction") or "").upper() == str(b.get("direction") or "").upper():
                same_side += 1
    gaps: list[float] = []
    seen_sym_ts: dict[str, int] = {}
    for s in sig_sorted:
        sym = str(s.get("symbol") or "")
        ts = int(s.get("detected_at_ms") or 0)
        if sym in seen_sym_ts:
            gaps.append((ts - seen_sym_ts[sym]) / 1000.0)
        seen_sym_ts[sym] = ts
    repeated_thesis = 0
    for s in snapshots:
        if "REPEATED_THESIS_NO_NEW_EDGE" in str(s.get("final_reason") or ""):
            repeated_thesis += 1
        if "REPEATED_THESIS_NO_NEW_EDGE" in list(s.get("contradicting_evidence") or []):
            repeated_thesis += 1
    sym_counts = Counter(str(s.get("symbol") or "") for s in signals)

    # O8 edge calibration
    pairs = [
        (float(r["expected_net_edge"]), float(r["post_cost_hypothetical"]))
        for r in joined
        if r.get("has_outcome")
        and _f(r.get("expected_net_edge")) is not None
        and _f(r.get("post_cost_hypothetical")) is not None
    ]
    pred_pos_real_neg = sum(1 for p, r in pairs if p > 0 and r < 0)
    pred_neg_real_pos = sum(1 for p, r in pairs if p < 0 and r > 0)
    pearson = _pearson([p for p, _ in pairs], [r for _, r in pairs])
    spearman = _spearman([p for p, _ in pairs], [r for _, r in pairs])
    edge_status = "INSUFFICIENT_SAMPLE"
    if len(pairs) >= 20:
        if (pearson is not None and pearson >= 0.2) or (spearman is not None and spearman >= 0.2):
            edge_status = "SOME_CALIBRATION_USEFULNESS"
        else:
            edge_status = "EDGE_MODEL_NOT_CALIBRATED"

    # O9 counterfactual per horizon (no auto-promotion)
    path_recs = path_records_for_counterfactual(campaign_root)
    cf_by_horizon: dict[str, Any] = {}
    for h in HORIZONS:
        subset = [p for p in path_recs if int(p.get("horizon_sec") or 0) == h]
        configs = []
        for cfg in RESEARCH_CONFIGS:
            rows = []
            for rec in subset:
                bars = list(rec.get("bars") or [])
                if not bars:
                    continue
                rows.append(
                    evaluate_ohlc_path(
                        entry_price=float(rec["entry_price"]),
                        direction=str(rec.get("direction") or "LONG"),
                        bars=bars,
                        stop_pct=float(cfg["stop_pct"]),
                        target_pct=float(cfg["target_pct"]),
                        notional=float(rec.get("notional") or 350.0),
                    )
                )
            configs.append({"config": cfg["name"], "auto_promoted": False, **_bucket_stats(rows),
                            "ambiguous_first_touch_count": sum(1 for r in rows if r.get("ambiguous_first_touch")),
                            "target_before_stop": sum(1 for r in rows if r.get("target_before_stop") is True),
                            "stop_before_target": sum(1 for r in rows if r.get("stop_before_target") is True),
                            })
        cf_by_horizon[HORIZON_LABELS[h]] = {"path_records": len(subset), "configs": configs}

    # O10 regime — from snapshots joined when possible
    regime_perf: dict[str, Any] = {}
    for rname, rows in by_regime.items():
        longs = [x for x in rows if str(x.get("direction") or "").upper() == "LONG"]
        shorts = [x for x in rows if str(x.get("direction") or "").upper() == "SHORT"]
        regime_perf[rname] = {
            "sample_count": len(rows),
            "LONG": _bucket_stats(longs),
            "SHORT": _bucket_stats(shorts),
            **_bucket_stats(rows),
        }

    # O11 data quality
    warn_c: Counter[str] = Counter()
    clean_rows: list[dict[str, Any]] = []
    dirty_rows: list[dict[str, Any]] = []
    for r in records:
        warns = list(r.get("data_quality_warnings") or [])
        mq = r.get("measurement_quality")
        if mq:
            warns.append(str(mq))
        if r.get("ambiguous_first_touch"):
            warns.append("AMBIGUOUS")
        for w in warns:
            warn_c[str(w)] += 1
        serious = any(
            x in {"ENTRY_CANDLE_PARTIAL", "OHLC_1M_LIMITED", "NO_PATH_DATA", "AMBIGUOUS", "LEGACY_CLOSE_ONLY_NOT_AUTHORITATIVE"}
            for x in warns
        )
        (dirty_rows if serious else clean_rows).append(r)

    # O12 product metrics foundation
    pos = sum(1 for r in joined if r.get("has_outcome") and (_f(r.get("post_cost_hypothetical")) or 0) > 0)
    neg = sum(1 for r in joined if r.get("has_outcome") and (_f(r.get("post_cost_hypothetical")) or 0) < 0)
    product = {
        "signal_count": len(signals),
        "positive_post_cost_outcomes": pos,
        "negative_post_cost_outcomes": neg,
        "expired": sum(1 for s in signals if s.get("lifecycle_state") == "EXPIRED"),
        "invalidated": sum(1 for s in signals if s.get("lifecycle_state") == "INVALIDATED"),
        "preserves_losers": True,
        "historical_similar_setup_stats": None,
    }

    # O13 split windows when enough matured (champion params only; no auto-promotion)
    half_split = None
    if gate_matured >= 200 and path_recs:
        champ = RESEARCH_CONFIGS[0]
        mid = len(path_recs) // 2
        a, b = path_recs[:mid], path_recs[mid:]

        def _eval_window(subset: list[dict[str, Any]]) -> dict[str, Any]:
            rows = [
                evaluate_ohlc_path(
                    entry_price=float(p["entry_price"]),
                    direction=str(p.get("direction") or "LONG"),
                    bars=list(p.get("bars") or []),
                    stop_pct=float(champ["stop_pct"]),
                    target_pct=float(champ["target_pct"]),
                    notional=float(p.get("notional") or 350.0),
                )
                for p in subset
                if p.get("bars")
            ]
            return {
                **_bucket_stats(rows),
                "symbol_concentration": dict(
                    Counter(str(p.get("symbol") or "") for p in subset).most_common(8)
                ),
                "regime_mix": "see_regime_performance_when_joined",
            }

        half_split = {
            "Window_A": _eval_window(a),
            "Window_B": _eval_window(b),
            "note": "non_overlapping_half_split_of_path_records_not_calendar_windows",
            "config": champ["name"],
            "auto_promoted": False,
        }

    # Staged checkpoint — canonical gate uses VALID fully matured all horizons
    next_stage = "EARLY_DIAGNOSTIC_AT_50_VALID_FULLY_MATURED"
    reached: list[str] = []
    for name, thr in STAGE_THRESHOLDS:
        if gate_matured >= thr:
            reached.append(name)
        else:
            next_stage = f"{name}_AT_{thr}_VALID_FULLY_MATURED"
            break
    else:
        next_stage = "PROMOTION_REVIEW_CANDIDATE_REACHED"

    if gate_matured < 50:
        observation_stage = "COLLECTING"
    elif gate_matured < 100:
        observation_stage = "EARLY_DIAGNOSTIC_READY"
    elif gate_matured < 200:
        observation_stage = "INTERMEDIATE_REVIEW_READY"
    else:
        observation_stage = "PROMOTION_REVIEW_CANDIDATE"

    bf = backfill_progress or {}
    report = {
        "schema": OBSERVATION_SCHEMA,
        "generated_at": _utc(),
        "runtime_commit": runtime_commit,
        "write_enabled": False,
        "demo_write_reenabled": False,
        "ready_for_demo_reenable": False,
        "strategy_changed": False,
        "risk_changed": False,
        "gate_lowered": False,
        "mainnet": False,
        "real_money": False,
        "files": files,
        "cycles_observed": cycles_observed,
        "signal_ledger_rows": led_stats["ledger_rows"],
        "unique_signals_created_total": unique_created,
        "signals_created": unique_created,
        "duplicate_signal_rows": led_stats["duplicate_signal_rows"],
        "path_record_rows": audit["path_record_rows"],
        "unique_path_keys": audit["unique_path_keys"],
        "duplicate_path_record_rows": audit["duplicate_path_record_rows"],
        "outcome_rows": audit["outcome_rows"],
        "unique_outcome_keys": audit["unique_outcome_keys"],
        "duplicate_outcome_rows": audit["duplicate_outcome_rows"],
        "path_records": audit["path_record_rows"],
        "path_record_rows_note": "NOT_a_unique_signal_count_may_be_upto_5x_horizons",
        "signals_matured_any_valid_horizon": len(matured_any_valid),
        "signals_matured_any_horizon": len(matured_any_valid),
        "signals_matured_valid_1m": matured_by_horizon.get("1m", 0),
        "signals_matured_valid_3m": matured_by_horizon.get("3m", 0),
        "signals_matured_valid_5m": matured_by_horizon.get("5m", 0),
        "signals_matured_valid_15m": matured_by_horizon.get("15m", 0),
        "signals_matured_valid_30m": matured_by_horizon.get("30m", 0),
        "signals_matured_1m": matured_by_horizon.get("1m", 0),
        "signals_matured_3m": matured_by_horizon.get("3m", 0),
        "signals_matured_5m": matured_by_horizon.get("5m", 0),
        "signals_matured_15m": matured_by_horizon.get("15m", 0),
        "signals_matured_30m": matured_by_horizon.get("30m", 0),
        "signals_fully_resolved_all_horizons": fully_resolved,
        "signals_fully_matured_valid_all_horizons": fully_valid,
        "signals_fully_matured_all_horizons": fully_valid,
        "signals_with_any_unavailable_horizon": with_unavail,
        "signals_invalid_for_promotion": invalid_promo,
        "canonical_promotion_maturity_metric": "signals_fully_matured_valid_all_horizons",
        "signals_matured": fully_valid,
        "pending_signal_count": pending,
        "historical_path_unavailable_count": unavailable_count,
        "backfill_status": backfill_status or bf.get("backfill_status"),
        "backfill_progress": _backfill_progress_fields(bf),
        "outcomes_rows": len(outcomes),
        "snapshots_latest_count": len(snapshots),
        "matured_by_horizon": matured_by_horizon,
        "observation_stage": observation_stage,
        "per_horizon": per_horizon,
        "state_counts": dict(state_counts),
        "score_buckets": score_buckets,
        "score_calibration": calibration,
        "entry_quality_buckets": {k: _bucket_stats(v) for k, v in by_eq.items()},
        "confidence_buckets": {k: _bucket_stats(v) for k, v in by_conf.items()},
        "expected_net_edge_buckets": {k: _bucket_stats(v) for k, v in by_edge.items()},
        "ready_watch_wait_validation": ready_watch,
        "evidence_associations": evidence_assoc,
        "anti_churn": {
            "same_symbol_consecutive_signals": same_sym,
            "same_side_consecutive_signals": same_side,
            "median_time_between_same_symbol_signals_sec": _median(gaps),
            "REPEATED_THESIS_NO_NEW_EDGE_count": repeated_thesis,
            "symbol_concentration": dict(sym_counts.most_common(10)),
            "top_10_symbols": sym_counts.most_common(10),
            "thesis_state_exists": thesis_path.exists(),
        },
        "edge_calibration": {
            "pair_count": len(pairs),
            "pearson": pearson,
            "spearman": spearman,
            "predicted_positive_realized_negative": pred_pos_real_neg,
            "predicted_negative_realized_positive": pred_neg_real_pos,
            "status": edge_status,
        },
        "counterfactual_by_horizon": cf_by_horizon,
        "regime_performance": regime_perf,
        "data_quality": {
            "warning_counts": dict(warn_c.most_common()),
            "clean_sample_count": len(clean_rows),
            "dirty_sample_count": len(dirty_rows),
            "clean_stats": _bucket_stats(clean_rows),
            "dirty_stats": _bucket_stats(dirty_rows),
        },
        "product_metrics_foundation": product,
        "promotion_split": half_split,
        "stages_reached": reached,
        "next_checkpoint": next_stage,
        "review_thresholds": {name: thr for name, thr in STAGE_THRESHOLDS},
        "historical_trade_audit": "PENDING",
    }

    # Persist latest + staged snapshots when thresholds crossed
    latest = d / "observation_latest.json"
    tmp = latest.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(latest)

    for name, thr in STAGE_THRESHOLDS:
        if gate_matured >= thr:
            staged = d / f"checkpoint_{name.lower()}.json"
            if not staged.exists():
                staged.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")

    return report
