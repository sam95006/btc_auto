"""V2-C1 Shadow Challenger persistence, ledger, and compact report."""
from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from backend.nexus_research_ai_autonomy.promotion_selectivity_research_v1 import summarize_outcomes
from backend.nexus_research_ai_autonomy.shadow_signal_v1 import (
    ensure_signal_state_entry,
    load_signal_state,
    save_signal_state,
    shadow_dir,
)
from backend.nexus_research_ai_autonomy.signal_quality_v2_c1 import (
    ACTION_COHORT_READY,
    CHALLENGER_VERSION,
    CHAMPION_VERSION,
    EVIDENCE_GENERATION,
    SELECTED_COHORT_NAME,
    audit_ready_threshold_provenance,
    is_selected_top1_long,
    materialize_v2_evidence,
    select_v2_c1_for_episode,
)
from backend.nexus_research_ai_autonomy.v2_c1_thesis_v1 import (
    ACTION_EVIDENCE_POST_ISOLATION,
    ACTION_EVIDENCE_PRE_ISOLATION,
    V1_THESIS_NAMESPACE,
    V2_THESIS_NAMESPACE,
    action_evidence_epoch,
    record_v2_c1_thesis,
    resolve_abstention_diagnostic,
)

V2_LEDGER = "v2_c1_shadow_signals.jsonl"
CYCLE_LEDGER = "shadow_champion_challenger_cycles.jsonl"
REPORT_PATH = "shadow_v2_challenger_latest.json"
VALIDATION_CHECKPOINTS = (25, 50, 100, 200)
REPORT_SCHEMA = "v30_shadow_v2_challenger_report_v3"


def v2_ledger_path(campaign_root: Path) -> Path:
    return shadow_dir(campaign_root) / V2_LEDGER


def cycle_ledger_path(campaign_root: Path) -> Path:
    return shadow_dir(campaign_root) / CYCLE_LEDGER


def report_path(campaign_root: Path) -> Path:
    return shadow_dir(campaign_root) / REPORT_PATH


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
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


def load_v2_c1_shadow_signals(campaign_root: Path) -> list[dict[str, Any]]:
    """Unique V2-C1 origin signals (POST_V2_FREEZE only)."""
    by_id: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(v2_ledger_path(campaign_root)):
        if row.get("evidence_generation") != EVIDENCE_GENERATION:
            continue
        sid = str(row.get("signal_id") or row.get("v2_signal_id") or "")
        if not sid or sid in by_id:
            continue
        by_id[sid] = row
    return list(by_id.values())


def load_selected_top1_long(campaign_root: Path) -> list[dict[str, Any]]:
    return [e for e in load_v2_c1_shadow_signals(campaign_root) if is_selected_top1_long(e)]


def episode_selected_top1_index(campaign_root: Path) -> dict[Any, list[dict[str, Any]]]:
    by_ep: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in load_selected_top1_long(campaign_root):
        ep = row.get("episode_id")
        if ep is not None:
            by_ep[ep].append(row)
    return dict(by_ep)


def count_duplicate_long_top1_episodes(campaign_root: Path) -> int:
    return sum(1 for rows in episode_selected_top1_index(campaign_root).values() if len(rows) > 1)


def evidence_to_shadow_signal(evidence: dict[str, Any]) -> dict[str, Any]:
    action = str(evidence.get("action") or "WAIT")
    # All selected Top1 LONG rows track outcomes regardless of action (R3).
    if evidence.get("outcome_eligible") or is_selected_top1_long(evidence):
        state = "READY" if action == "READY" else ("WATCH" if action == "WATCH" else "DETECTED")
    else:
        state = "READY" if action == "READY" else ("WATCH" if action == "WATCH" else "DETECTED")
    prov = evidence.get("regime_provenance") or {}
    return {
        "schema": "v30_v2_c1_shadow_signal_v1",
        "signal_id": evidence.get("signal_id"),
        "v2_signal_id": evidence.get("v2_signal_id"),
        "challenger_version": CHALLENGER_VERSION,
        "evidence_generation": EVIDENCE_GENERATION,
        "lifecycle_state": state,
        "detected_at_ms": evidence.get("detected_at_ms"),
        "symbol": evidence.get("symbol"),
        "direction": evidence.get("direction"),
        "entry_price": evidence.get("entry_price"),
        "expected_net_edge": evidence.get("expected_net_edge"),
        "entry_quality_score": evidence.get("score"),
        "supporting_evidence": list(evidence.get("supporting_evidence") or []),
        "contradicting_evidence": list(evidence.get("contradicting_evidence") or []),
        "regime": prov.get("engine_regime"),
        "market_structure": prov.get("market_structure"),
        "lane": evidence.get("lane"),
        "selected_cohort": evidence.get("selected_cohort"),
        "action_cohort": evidence.get("action_cohort"),
        "outcome_eligible": bool(evidence.get("outcome_eligible")),
        "action": action,
        "outcome": None,
    }


def persist_v2_evidence(campaign_root: Path, evidence_rows: list[dict[str, Any]]) -> int:
    if not evidence_rows:
        return 0
    d = shadow_dir(campaign_root)
    d.mkdir(parents=True, exist_ok=True)
    ledger = v2_ledger_path(campaign_root)
    existing_ids = {str(r.get("signal_id") or "") for r in load_v2_c1_shadow_signals(campaign_root)}
    existing_eps = {
        r.get("episode_id")
        for r in load_selected_top1_long(campaign_root)
        if r.get("episode_id") is not None
    }
    new_rows: list[dict[str, Any]] = []
    for row in evidence_rows:
        sid = str(row.get("signal_id") or "")
        if not sid or sid in existing_ids:
            continue
        if is_selected_top1_long(row):
            ep = row.get("episode_id")
            if ep is not None and ep in existing_eps:
                continue
            if ep is not None:
                existing_eps.add(ep)
        new_rows.append(row)
    if new_rows:
        with ledger.open("a", encoding="utf-8") as fh:
            for row in new_rows:
                fh.write(json.dumps(row, default=str) + "\n")
        state = load_signal_state(campaign_root)
        for row in new_rows:
            ensure_signal_state_entry(state, evidence_to_shadow_signal(row))
        save_signal_state(campaign_root, state)
    return len(new_rows)


def persist_champion_challenger_cycle(campaign_root: Path, cycle_row: dict[str, Any]) -> None:
    d = shadow_dir(campaign_root)
    d.mkdir(parents=True, exist_ok=True)
    path = cycle_ledger_path(campaign_root)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(cycle_row, default=str) + "\n")


def _path_rows_for_signals(
    campaign_root: Path,
    signals: list[dict[str, Any]],
    *,
    horizon_sec: int,
    action_filter: str | None = "READY",
) -> list[dict[str, Any]]:
    from backend.nexus_research_ai_autonomy.shadow_path_index_v1 import (
        ensure_path_index,
        index_key_status,
        iter_jsonl_dicts,
        path_records_path,
    )

    index = ensure_path_index(campaign_root)
    key_status = index_key_status(index)
    wanted: set[tuple[str, int]] = set()
    meta: dict[str, dict[str, Any]] = {}
    for sig in signals:
        if action_filter == "READY":
            action = str(sig.get("lifecycle_state") or sig.get("action") or "")
            if action != "READY":
                continue
        sid = str(sig.get("signal_id") or "")
        if not sid:
            continue
        wanted.add((sid, int(horizon_sec)))
        meta[sid] = sig
    if not wanted:
        return []
    out: list[dict[str, Any]] = []
    for rec in iter_jsonl_dicts(path_records_path(campaign_root)):
        sid = str(rec.get("signal_id") or "")
        h = int(rec.get("horizon_sec") or 0)
        if (sid, h) not in wanted:
            continue
        if key_status.get((sid, h)) == "UNAVAILABLE" or rec.get("unavailable_reason"):
            continue
        sig = meta.get(sid) or {}
        out.append({**rec, "symbol": sig.get("symbol"), "direction": sig.get("direction")})
    return out


def _checkpoint_block(prefix: str, count: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for n in VALIDATION_CHECKPOINTS:
        out[f"{prefix}_{n}"] = {
            "target": n,
            "reached": count >= n,
            "fully_valid_count": count,
        }
    return out


def _fully_valid_count(evidence_rows: list[dict[str, Any]], state: dict[str, Any]) -> int:
    n = 0
    for e in evidence_rows:
        sid = str(e.get("signal_id") or "")
        ent = state.get(sid) or {}
        if ent.get("fully_matured_valid_all_horizons"):
            n += 1
    return n


def build_shadow_v2_challenger_report(campaign_root: Path) -> dict[str, Any]:
    from backend.nexus_research_ai_autonomy.shadow_signal_v1 import load_active_shadow_signals

    cycles = _read_jsonl(cycle_ledger_path(campaign_root))
    v2_evidence = load_v2_c1_shadow_signals(campaign_root)
    selected_top1 = load_selected_top1_long(campaign_root)
    v1_signals = load_active_shadow_signals(campaign_root)
    selected_shadow = [evidence_to_shadow_signal(e) for e in selected_top1]
    post_isolation = [e for e in selected_top1 if action_evidence_epoch(e) == ACTION_EVIDENCE_POST_ISOLATION]
    pre_isolation = [e for e in selected_top1 if action_evidence_epoch(e) == ACTION_EVIDENCE_PRE_ISOLATION]
    ready_evidence = [e for e in selected_top1 if str(e.get("action")) == "READY"]
    post_ready_evidence = [
        e for e in ready_evidence if action_evidence_epoch(e) == ACTION_EVIDENCE_POST_ISOLATION
    ]
    ready_shadow = [evidence_to_shadow_signal(e) for e in post_ready_evidence]
    post_ready_shadow = ready_shadow
    v2_short = [e for e in v2_evidence if e.get("lane") == "SHORT_SHADOW_RESEARCH"]
    v1_ready = [s for s in v1_signals if str(s.get("lifecycle_state")) == "READY"]
    state = load_signal_state(campaign_root).get("signals") or {}

    episodes = {c.get("episode_id") for c in cycles if c.get("episode_id") is not None}
    action_dist = Counter(str(e.get("action") or "UNKNOWN") for e in selected_top1)
    reason_dist = Counter(str(e.get("reason") or "UNKNOWN") for e in selected_top1)
    abstention_diag = Counter(resolve_abstention_diagnostic(e) for e in selected_top1)
    post_action_dist = Counter(str(e.get("action") or "UNKNOWN") for e in post_isolation)
    post_reason_dist = Counter(str(e.get("reason") or "UNKNOWN") for e in post_isolation)
    post_abstention_diag = Counter(resolve_abstention_diagnostic(e) for e in post_isolation)
    legacy_missing_count = sum(1 for e in selected_top1 if resolve_abstention_diagnostic(e) == "legacy_missing")

    def _horizon(horizon_sec: int, signals: list[dict[str, Any]], *, action_filter: str | None) -> dict[str, Any]:
        rows = _path_rows_for_signals(
            campaign_root, signals, horizon_sec=horizon_sec, action_filter=action_filter
        )
        return summarize_outcomes(rows)

    selected_fully_valid = _fully_valid_count(selected_top1, state)
    ready_fully_valid = _fully_valid_count(post_ready_evidence, state)

    sym_counter: Counter[str] = Counter(str(e.get("symbol") or "") for e in selected_top1)
    regime_counter: Counter[str] = Counter()
    cost_drag: list[float] = []
    for e in selected_top1:
        prov = e.get("regime_provenance") or {}
        regime_counter[str(prov.get("engine_regime") or "UNKNOWN")] += 1
        tc = e.get("estimated_total_cost")
        if tc is not None:
            cost_drag.append(float(tc))

    abstentions = sum(1 for e in selected_top1 if str(e.get("action")) != "READY")
    abstention_rate = round(abstentions / max(1, len(selected_top1)), 4)

    return {
        "schema": REPORT_SCHEMA,
        "updated_at_ms": int(time.time() * 1000),
        "champion_version": CHAMPION_VERSION,
        "challenger_version": CHALLENGER_VERSION,
        "evidence_generation": EVIDENCE_GENERATION,
        "v1_thesis_namespace": V1_THESIS_NAMESPACE,
        "v2_thesis_namespace": V2_THESIS_NAMESPACE,
        "champion_challenger_thesis_isolated": True,
        "action_evidence_generation": ACTION_EVIDENCE_POST_ISOLATION,
        "pre_isolation_action_count": len(pre_isolation),
        "post_isolation_action_count": len(post_isolation),
        "legacy_missing_diagnostic_count": legacy_missing_count,
        "post_isolation_action_distribution": dict(post_action_dist),
        "post_isolation_reason_distribution": dict(post_reason_dist),
        "post_isolation_abstention_diagnostic": dict(post_abstention_diag),
        "ready_threshold_provenance": audit_ready_threshold_provenance(),
        "selected_cohort_name": SELECTED_COHORT_NAME,
        "action_cohort_ready_name": ACTION_COHORT_READY,
        "primary_validation_counter": "SELECTED_TOP1_LONG",
        "ready_validation_counter": "SEPARATE",
        "cycles_observed": len(cycles),
        "episodes_observed": len(episodes),
        "duplicate_long_top1_episode_count": count_duplicate_long_top1_episodes(campaign_root),
        "v1_signals": len(v1_signals),
        "v1_ready": len(v1_ready),
        "v2_candidates": len(v2_evidence),
        "selected_top1_long_count": len(selected_top1),
        "selected_top1_fully_valid_count": selected_fully_valid,
        "selected_top1_action_distribution": dict(action_dist),
        "selected_top1_reason_distribution": dict(reason_dist),
        "selected_abstention_diagnostic": dict(abstention_diag),
        "v2_ready": len(post_ready_evidence),
        "v2_ready_fully_valid_count": ready_fully_valid,
        "v2_abstention_rate": abstention_rate,
        "v2_short_research_count": len(v2_short),
        "selected_top1_horizons": {
            "5m": _horizon(300, selected_shadow, action_filter=None),
            "15m": _horizon(900, selected_shadow, action_filter=None),
            "30m": _horizon(1800, selected_shadow, action_filter=None),
        },
        "selected_top1_symbol_concentration": dict(sym_counter.most_common(10)),
        "ready_horizons": {
            "5m": _horizon(300, post_ready_shadow, action_filter="READY"),
            "15m": _horizon(900, post_ready_shadow, action_filter="READY"),
            "30m": _horizon(1800, post_ready_shadow, action_filter="READY"),
            "note": "POST_V2_THESIS_ISOLATION action cohort only",
        },
        "horizons": {
            "15m": {
                "v1_ready": _horizon(900, v1_ready, action_filter=None),
                "selected_top1": _horizon(900, selected_shadow, action_filter=None),
                "v2_ready": _horizon(900, post_ready_shadow, action_filter="READY"),
            },
            "30m": {
                "v1_ready": _horizon(1800, v1_ready, action_filter=None),
                "selected_top1": _horizon(1800, selected_shadow, action_filter=None),
                "v2_ready": _horizon(1800, post_ready_shadow, action_filter="READY"),
            },
        },
        "regime_distribution": dict(regime_counter),
        "cost_drag": {
            "mean_estimated_total_cost": round(sum(cost_drag) / len(cost_drag), 6) if cost_drag else None,
            "fee_baseline_rt": 0.0011,
        },
        "validation_gates": {
            "selected_top1_long": _checkpoint_block("selected_checkpoint", selected_fully_valid),
            "v2_ready": _checkpoint_block("ready_checkpoint", ready_fully_valid),
            "v2_ready_note": "POST_V2_THESIS_ISOLATION action cohort only",
            "early_challenger_diagnostic": {
                "at_n": 50,
                "counter": "SELECTED_TOP1_LONG",
                "reached": selected_fully_valid >= 50,
                "note": "Early Challenger Diagnostic on frozen Top1 selection cohort",
            },
            "intermediate_challenger_review": {
                "at_n": 100,
                "counter": "SELECTED_TOP1_LONG",
                "reached": selected_fully_valid >= 100,
            },
            "promotion_review_candidate": {
                "at_n": 200,
                "counter": "SELECTED_TOP1_LONG",
                "reached": selected_fully_valid >= 200,
                "note": "Promotion Review Candidate — no auto Demo enable",
            },
        },
        "promotion_auto_enable": False,
        "ready_for_demo_reenable": False,
    }


def write_shadow_v2_challenger_report(campaign_root: Path) -> Path:
    d = shadow_dir(campaign_root)
    d.mkdir(parents=True, exist_ok=True)
    path = report_path(campaign_root)
    payload = build_shadow_v2_challenger_report(campaign_root)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def run_v2_c1_shadow_challenger(
    *,
    campaign_root: Path,
    cycle_id: str,
    now_ms: int,
    ranked_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run V2-C1 from same PIT ranked rows; persist challenger evidence + cycle row."""
    selection = select_v2_c1_for_episode(ranked_rows, campaign_root=campaign_root, now_ms=now_ms)
    evidence = materialize_v2_evidence(selection, cycle_id=cycle_id, now_ms=now_ms)
    persisted = persist_v2_evidence(campaign_root, evidence)

    long_top1 = selection.get("long_top1") or {}
    if str(long_top1.get("v2_action")) == "READY":
        thesis_snap = long_top1.get("thesis_snapshot")
        if isinstance(thesis_snap, dict):
            record_v2_c1_thesis(campaign_root, thesis_snap)

    v1c = long_top1.get("v1_champion") or {}
    top_v1 = ranked_rows[0] if ranked_rows else {}
    ep_id = selection.get("episode_id")
    skipped_duplicate_episode = bool(
        ep_id is not None
        and ep_id in episode_selected_top1_index(campaign_root)
        and persisted == 0
        and any(is_selected_top1_long(e) for e in evidence)
    )
    cycle_row = {
        "schema": "v30_shadow_champion_challenger_cycle_v1",
        "champion_version": CHAMPION_VERSION,
        "challenger_version": CHALLENGER_VERSION,
        "evidence_generation": EVIDENCE_GENERATION,
        "thesis_namespace": V2_THESIS_NAMESPACE,
        "action_evidence_generation": ACTION_EVIDENCE_POST_ISOLATION,
        "cycle_id": cycle_id,
        "timestamp_ms": now_ms,
        "episode_id": ep_id,
        "episode_started_at_ms": selection.get("episode_started_at_ms"),
        "episode_window_sec": selection.get("episode_window_sec"),
        "selected_cohort": SELECTED_COHORT_NAME,
        "v1_action": v1c.get("action") or top_v1.get("final_action"),
        "v1_rank": v1c.get("rank") or (top_v1.get("snapshot") or {}).get("rank"),
        "v1_score": v1c.get("score") or top_v1.get("entry_quality_score"),
        "v2_action": long_top1.get("v2_action"),
        "v2_rank": long_top1.get("v2_rank"),
        "v2_score": long_top1.get("entry_quality_score"),
        "v2_lane": SELECTED_COHORT_NAME,
        "abstention_diagnostic": long_top1.get("abstention_diagnostic"),
        "short_research_action": (selection.get("short_research_top1") or {}).get("v2_action"),
        "short_research_rank": (selection.get("short_research_top1") or {}).get("v2_rank"),
        "long_candidates_in_episode": selection.get("long_candidates_count"),
        "zero_ready_valid": str(long_top1.get("v2_action") or "") != "READY",
        "skipped_duplicate_episode": skipped_duplicate_episode,
    }
    persist_champion_challenger_cycle(campaign_root, cycle_row)
    report_file = write_shadow_v2_challenger_report(campaign_root)

    return {
        "schema": "v30_v2_c1_challenger_cycle_result_v1",
        "champion_version": CHAMPION_VERSION,
        "challenger_version": CHALLENGER_VERSION,
        "evidence_generation": EVIDENCE_GENERATION,
        "selected_cohort": SELECTED_COHORT_NAME,
        "episode_id": ep_id,
        "v2_evidence_persisted": persisted,
        "skipped_duplicate_episode": skipped_duplicate_episode,
        "v2_long_top1_action": long_top1.get("v2_action"),
        "v2_abstention_diagnostic": long_top1.get("abstention_diagnostic"),
        "v2_short_research_action": (selection.get("short_research_top1") or {}).get("v2_action"),
        "report_path": str(report_file),
        "cycle_row": cycle_row,
    }
