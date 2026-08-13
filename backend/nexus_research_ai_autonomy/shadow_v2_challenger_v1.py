"""V2-C1 Shadow Challenger persistence, ledger, and compact report."""
from __future__ import annotations

import json
import time
from collections import Counter
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
    CHALLENGER_VERSION,
    CHAMPION_VERSION,
    EVIDENCE_GENERATION,
    materialize_v2_evidence,
    select_v2_c1_for_episode,
)

V2_LEDGER = "v2_c1_shadow_signals.jsonl"
CYCLE_LEDGER = "shadow_champion_challenger_cycles.jsonl"
REPORT_PATH = "shadow_v2_challenger_latest.json"
VALIDATION_CHECKPOINTS = (25, 50, 100, 200)


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


def evidence_to_shadow_signal(evidence: dict[str, Any]) -> dict[str, Any]:
    action = str(evidence.get("action") or "WAIT")
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
        "outcome": None,
    }


def persist_v2_evidence(campaign_root: Path, evidence_rows: list[dict[str, Any]]) -> int:
    if not evidence_rows:
        return 0
    d = shadow_dir(campaign_root)
    d.mkdir(parents=True, exist_ok=True)
    ledger = v2_ledger_path(campaign_root)
    existing = {str(r.get("signal_id") or "") for r in load_v2_c1_shadow_signals(campaign_root)}
    new_rows = [r for r in evidence_rows if str(r.get("signal_id") or "") not in existing]
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


def _validation_gates(v2_ready_fully_valid: int) -> dict[str, Any]:
    gates: dict[str, Any] = {}
    for n in VALIDATION_CHECKPOINTS:
        reached = v2_ready_fully_valid >= n
        label = f"checkpoint_{n}"
        gates[label] = {
            "target_fully_valid_v2_ready": n,
            "reached": reached,
            "fully_valid_v2_ready_count": v2_ready_fully_valid,
        }
    gates["early_challenger_diagnostic"] = {
        "at_n": 50,
        "reached": v2_ready_fully_valid >= 50,
        "note": "Early Challenger Diagnostic — founder review only",
    }
    gates["intermediate_challenger_review"] = {
        "at_n": 100,
        "reached": v2_ready_fully_valid >= 100,
        "note": "Intermediate Challenger Review — founder review only",
    }
    gates["promotion_review_candidate"] = {
        "at_n": 200,
        "reached": v2_ready_fully_valid >= 200,
        "note": "Promotion Review Candidate — no auto Demo enable",
    }
    return gates


def build_shadow_v2_challenger_report(campaign_root: Path) -> dict[str, Any]:
    from backend.nexus_research_ai_autonomy.shadow_signal_v1 import load_active_shadow_signals, load_signal_state

    cycles = _read_jsonl(cycle_ledger_path(campaign_root))
    v2_evidence = load_v2_c1_shadow_signals(campaign_root)
    v1_signals = load_active_shadow_signals(campaign_root)
    v2_shadow = [evidence_to_shadow_signal(e) for e in v2_evidence]
    state = load_signal_state(campaign_root).get("signals") or {}

    episodes = {c.get("episode_id") for c in cycles if c.get("episode_id") is not None}
    v2_ready = [e for e in v2_evidence if str(e.get("action")) == "READY"]
    v2_long = [e for e in v2_evidence if e.get("lane") == "LONG_TOP1"]
    v2_short = [e for e in v2_evidence if e.get("lane") == "SHORT_SHADOW_RESEARCH"]
    v1_ready = [s for s in v1_signals if str(s.get("lifecycle_state")) == "READY"]

    abstentions = sum(1 for e in v2_long if str(e.get("action")) != "READY")
    abstention_rate = round(abstentions / max(1, len(v2_long)), 4)

    def _horizon_summary(signals: list[dict[str, Any]], horizon_sec: int) -> dict[str, Any]:
        rows = _path_rows_for_signals(campaign_root, signals, horizon_sec=horizon_sec, action_filter="READY")
        return summarize_outcomes(rows)

    v1_15 = _horizon_summary(v1_ready, 900)
    v1_30 = _horizon_summary(v1_ready, 1800)
    v2_15 = _horizon_summary(v2_shadow, 900)
    v2_30 = _horizon_summary(v2_shadow, 1800)

    sym_counter: Counter[str] = Counter()
    regime_counter: Counter[str] = Counter()
    cost_drag: list[float] = []
    for e in v2_evidence:
        sym_counter[str(e.get("symbol") or "")] += 1
        prov = e.get("regime_provenance") or {}
        regime_counter[str(prov.get("engine_regime") or "UNKNOWN")] += 1
        tc = e.get("estimated_total_cost")
        if tc is not None:
            cost_drag.append(float(tc))

    fully_valid_v2_ready = 0
    for e in v2_ready:
        sid = str(e.get("signal_id") or "")
        ent = state.get(sid) or {}
        if ent.get("fully_matured_valid_all_horizons"):
            fully_valid_v2_ready += 1

    return {
        "schema": "v30_shadow_v2_challenger_report_v1",
        "updated_at_ms": int(time.time() * 1000),
        "champion_version": CHAMPION_VERSION,
        "challenger_version": CHALLENGER_VERSION,
        "evidence_generation": EVIDENCE_GENERATION,
        "cycles_observed": len(cycles),
        "episodes_observed": len(episodes),
        "v1_signals": len(v1_signals),
        "v1_ready": len(v1_ready),
        "v2_candidates": len(v2_evidence),
        "v2_ready": len(v2_ready),
        "v2_abstention_rate": abstention_rate,
        "v2_long_count": len(v2_long),
        "v2_short_research_count": len(v2_short),
        "horizons": {
            "15m": {
                "v1_ready": v1_15,
                "v2_ready": v2_15,
            },
            "30m": {
                "v1_ready": v1_30,
                "v2_ready": v2_30,
            },
        },
        "symbol_concentration": dict(sym_counter.most_common(10)),
        "regime_distribution": dict(regime_counter),
        "cost_drag": {
            "mean_estimated_total_cost": round(sum(cost_drag) / len(cost_drag), 6) if cost_drag else None,
            "fee_baseline_rt": 0.0011,
        },
        "validation_gates": _validation_gates(fully_valid_v2_ready),
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
    v1c = long_top1.get("v1_champion") or {}
    top_v1 = ranked_rows[0] if ranked_rows else {}
    cycle_row = {
        "schema": "v30_shadow_champion_challenger_cycle_v1",
        "champion_version": CHAMPION_VERSION,
        "challenger_version": CHALLENGER_VERSION,
        "evidence_generation": EVIDENCE_GENERATION,
        "cycle_id": cycle_id,
        "timestamp_ms": now_ms,
        "episode_id": selection.get("episode_id"),
        "episode_started_at_ms": selection.get("episode_started_at_ms"),
        "episode_window_sec": selection.get("episode_window_sec"),
        "v1_action": v1c.get("action") or top_v1.get("final_action"),
        "v1_rank": v1c.get("rank") or (top_v1.get("snapshot") or {}).get("rank"),
        "v1_score": v1c.get("score") or top_v1.get("entry_quality_score"),
        "v2_action": long_top1.get("v2_action"),
        "v2_rank": long_top1.get("v2_rank"),
        "v2_score": long_top1.get("entry_quality_score"),
        "v2_lane": "LONG_TOP1",
        "short_research_action": (selection.get("short_research_top1") or {}).get("v2_action"),
        "short_research_rank": (selection.get("short_research_top1") or {}).get("v2_rank"),
        "long_candidates_in_episode": selection.get("long_candidates_count"),
        "zero_ready_valid": str(long_top1.get("v2_action") or "") != "READY",
    }
    persist_champion_challenger_cycle(campaign_root, cycle_row)
    report_file = write_shadow_v2_challenger_report(campaign_root)

    return {
        "schema": "v30_v2_c1_challenger_cycle_result_v1",
        "champion_version": CHAMPION_VERSION,
        "challenger_version": CHALLENGER_VERSION,
        "evidence_generation": EVIDENCE_GENERATION,
        "episode_id": selection.get("episode_id"),
        "v2_evidence_persisted": persisted,
        "v2_long_top1_action": long_top1.get("v2_action"),
        "v2_short_research_action": (selection.get("short_research_top1") or {}).get("v2_action"),
        "report_path": str(report_file),
        "cycle_row": cycle_row,
    }
