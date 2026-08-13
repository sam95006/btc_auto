"""Signal Quality V2-C1 Shadow Challenger — LONG score Top1 per episode.

Champion V1 frozen. V2-C1 is shadow-only; no Demo orders.
Ranking uses entry_quality_score (same semantics as rank_by_score research).
"""
from __future__ import annotations

import uuid
from typing import Any

from backend.nexus_research_ai_autonomy.anti_churn_thesis_v1 import evaluate_thesis_novelty
from backend.nexus_research_ai_autonomy.regime_provenance_v1 import attach_regime_provenance
from backend.nexus_research_ai_autonomy.signal_quality_v1 import (
    build_evidence_lists,
    compute_entry_quality,
    compute_expected_net_edge,
    estimate_round_trip_fee,
)

CHAMPION_VERSION = "V1"
CHALLENGER_VERSION = "V2_C1"
EPISODE_WINDOW_SEC = 120
FEE_RT = 0.0011
NOTIONAL = 350.0
COST_RESEARCH_MULTIPLIERS = (1.0, 1.25, 1.5, 2.0)
EVIDENCE_GENERATION = "POST_V2_FREEZE"
HISTORICAL_FIT_NOTE = "202-sample LONG top1 used to SELECT C1; not promotion evidence"

# Frozen C1 selection hypothesis = LONG + SCORE rank Top1 per 120s episode (no action filter).
SELECTED_COHORT_NAME = "V2_C1_SELECTED_TOP1_LONG"
ACTION_COHORT_READY = "V2_C1_READY"
SELECTED_LANE = "LONG_TOP1"

# Action thresholds copied from V1 _action_from_scores — inherited gates, NOT selection criteria.
READY_ENTRY_QUALITY = 0.65
WATCH_ENTRY_QUALITY = 0.50
READY_EDGE_RATIO = 1.2
THRESHOLD_PROVENANCE = {
    "entry_quality_065": {
        "provenance": "INHERITED_EXISTING_GATE",
        "source": "signal_quality_cycle_v1._action_from_scores (V1 SELECT/READY)",
        "part_of_frozen_c1_selection": False,
    },
    "watch_050": {
        "provenance": "INHERITED_EXISTING_GATE",
        "source": "signal_quality_cycle_v1._action_from_scores (V1 WATCH)",
        "part_of_frozen_c1_selection": False,
    },
    "edge_ratio_120": {
        "provenance": "INHERITED_EXISTING_GATE",
        "source": "signal_quality_cycle_v1._action_from_scores (V1 SELECT/READY edge_to_cost_ratio)",
        "part_of_frozen_c1_selection": False,
    },
}


def audit_ready_threshold_provenance() -> dict[str, Any]:
    """R1 — document threshold lineage; inherited V1 gates are not C1 selection criteria."""
    return dict(THRESHOLD_PROVENANCE)


def episode_id_from_ms(ts_ms: int, *, window_sec: int = EPISODE_WINDOW_SEC) -> int:
    return int(ts_ms) // (int(window_sec) * 1000)


def _critical_contradiction(contradict: list[str], edge: dict[str, Any]) -> str | None:
    if "POST_COST_EDGE_NEGATIVE" in contradict:
        return "POST_COST_EDGE_NEGATIVE"
    if "SPREAD_WIDE" in contradict:
        return "SPREAD_WIDE"
    if "REGIME_UNCERTAIN" in contradict:
        return "REGIME_UNCERTAIN"
    if (edge.get("expected_net_edge") or 0) <= 0 and "POST_COST_EDGE_NEGATIVE" not in contradict:
        return "POST_COST_EDGE_NEGATIVE"
    return None


def _v2_abstention_action(
    *,
    entry_quality: float,
    expected_net_edge: float,
    edge_ratio: float | None,
    thesis_ok: bool,
    gate_pass: bool,
    contradict: list[str],
    direction: str,
) -> tuple[str, str]:
    if direction.upper() == "SHORT":
        return "WATCH", "SHORT_SHADOW_RESEARCH"
    if not thesis_ok:
        return "BLOCK", "REPEATED_THESIS_NO_NEW_EDGE"
    if not gate_pass:
        return "WAIT", "GATES_NOT_PASSED"
    if expected_net_edge <= 0:
        return "WAIT", "POST_COST_EDGE_NEGATIVE"
    crit = _critical_contradiction(contradict, {"expected_net_edge": expected_net_edge})
    if crit:
        return "WAIT", crit
    if (
        entry_quality >= READY_ENTRY_QUALITY
        and expected_net_edge > 0
        and (edge_ratio or 0) >= READY_EDGE_RATIO
    ):
        return "READY", "V2_C1_LONG_TOP1_READY"
    if entry_quality >= WATCH_ENTRY_QUALITY and expected_net_edge > 0:
        return "WATCH", "V2_C1_LONG_TOP1_WATCH"
    return "WAIT", "INSUFFICIENT_ENTRY_QUALITY"


def classify_abstention_diagnostic(candidate: dict[str, Any]) -> str:
    """R6 — compact abstention reason bucket for Founder telemetry."""
    action = str(candidate.get("v2_action") or candidate.get("action") or "")
    reason = str(candidate.get("v2_reason") or candidate.get("reason") or "")
    if action == "READY":
        return "ready"
    if not candidate.get("thesis_ok") or "REPEATED_THESIS" in reason:
        return "repeated_thesis"
    if not candidate.get("gate_pass") or reason == "GATES_NOT_PASSED":
        return "gate_not_passed"
    if reason == "POST_COST_EDGE_NEGATIVE" or float(candidate.get("expected_net_edge") or 0) <= 0:
        return "post_cost_edge_negative"
    if candidate.get("critical_contradiction"):
        return "critical_contradiction"
    eq = float(candidate.get("entry_quality_score") or candidate.get("score") or 0)
    ratio = float(candidate.get("edge_to_cost_ratio") or 0)
    if action == "WATCH" and eq >= READY_ENTRY_QUALITY and ratio < READY_EDGE_RATIO:
        return "edge_ratio_threshold"
    if reason == "INSUFFICIENT_ENTRY_QUALITY" or eq < WATCH_ENTRY_QUALITY:
        return "entry_quality_threshold"
    return "other"


def _cost_hurdle_research(edge: dict[str, Any]) -> dict[str, float | None]:
    total = float(edge.get("estimated_round_trip_fee") or 0) + float(
        edge.get("estimated_spread_cost") or 0
    ) + float(edge.get("estimated_slippage_cost") or 0) + float(edge.get("estimated_funding_cost") or 0)
    net = float(edge.get("expected_net_edge") or 0)
    out: dict[str, float | None] = {}
    for m in COST_RESEARCH_MULTIPLIERS:
        hurdle = total * m
        out[f"M_{m}"] = round(net - hurdle, 6) if total > 0 else None
    return out


def build_long_candidate_row(
    row: dict[str, Any],
    *,
    campaign_root: Any,
) -> dict[str, Any] | None:
    enrichment = row.get("enrichment")
    regime_info = row.get("regime_info")
    if not isinstance(enrichment, dict) or not isinstance(regime_info, dict):
        return None
    regime_info = attach_regime_provenance(regime_info, enrichment=enrichment)
    structure = regime_info.get("market_structure") or "UNDETERMINED"
    regime = regime_info.get("regime") or "UNCERTAIN"
    edge = compute_expected_net_edge(enrichment=enrichment, side="LONG", notional=NOTIONAL)
    entry_q = compute_entry_quality(
        enrichment, side="LONG", structure=str(structure), regime=str(regime), edge=edge
    )
    support, contradict = build_evidence_lists(
        enrichment, side="LONG", structure=str(structure), regime=str(regime), edge=edge
    )
    gate_pass = bool(row.get("gate_pass", True))
    thesis = evaluate_thesis_novelty(
        campaign_root=campaign_root,
        symbol=str(row.get("symbol") or enrichment.get("symbol") or ""),
        side="LONG",
        current_snapshot={**enrichment, **regime_info, **edge, "side": "LONG"},
    )
    eq = float(entry_q.get("entry_quality_score") or 0)
    action, reason = _v2_abstention_action(
        entry_quality=eq,
        expected_net_edge=float(edge.get("expected_net_edge") or 0),
        edge_ratio=edge.get("edge_to_cost_ratio"),
        thesis_ok=bool(thesis.get("pass")),
        gate_pass=gate_pass,
        contradict=contradict + ([] if thesis.get("pass") else ["REPEATED_THESIS_NO_NEW_EDGE"]),
        direction="LONG",
    )
    snap = row.get("snapshot") or {}
    v1 = {
        "action": snap.get("final_action"),
        "rank": snap.get("rank"),
        "score": snap.get("entry_quality_score"),
        "expected_edge": snap.get("expected_net_edge"),
    }
    return {
        "symbol": row.get("symbol") or enrichment.get("symbol"),
        "direction": "LONG",
        "entry_quality_score": eq,
        "raw_quality_score": eq,
        "expected_net_edge": edge.get("expected_net_edge"),
        "expected_gross_edge": edge.get("expected_gross_edge"),
        "estimated_fee": edge.get("estimated_round_trip_fee"),
        "estimated_spread": edge.get("estimated_spread_cost"),
        "estimated_slippage": edge.get("estimated_slippage_cost"),
        "estimated_funding": edge.get("estimated_funding_cost"),
        "estimated_total_cost": round(
            float(edge.get("estimated_round_trip_fee") or 0)
            + float(edge.get("estimated_spread_cost") or 0)
            + float(edge.get("estimated_slippage_cost") or 0)
            + float(edge.get("estimated_funding_cost") or 0),
            6,
        ),
        "cost_hurdle_research": _cost_hurdle_research(edge),
        "supporting_evidence": support,
        "contradicting_evidence": contradict,
        "critical_contradiction": _critical_contradiction(contradict, edge),
        "regime_provenance": {
            "engine_regime": regime_info.get("engine_regime"),
            "market_structure": regime_info.get("market_structure"),
            "regime_source": regime_info.get("regime_source"),
            "regime_timestamp_ms": regime_info.get("regime_timestamp_ms"),
            "regime_confidence": regime_info.get("regime_confidence"),
            "mapping_version": regime_info.get("mapping_version"),
        },
        "v2_action": action,
        "v2_reason": reason if thesis.get("pass") else str(thesis.get("reason")),
        "v1_champion": v1,
        "enrichment": enrichment,
        "price": enrichment.get("price"),
        "detected_at_ms": int(enrichment.get("timestamp_ms") or row.get("timestamp_ms") or 0),
        "gate_pass": gate_pass,
        "thesis_ok": bool(thesis.get("pass")),
        "edge_to_cost_ratio": edge.get("edge_to_cost_ratio"),
        "abstention_diagnostic": classify_abstention_diagnostic(
            {
                "v2_action": action,
                "v2_reason": reason if thesis.get("pass") else str(thesis.get("reason")),
                "gate_pass": gate_pass,
                "thesis_ok": bool(thesis.get("pass")),
                "expected_net_edge": edge.get("expected_net_edge"),
                "critical_contradiction": _critical_contradiction(contradict, edge),
                "entry_quality_score": eq,
                "edge_to_cost_ratio": edge.get("edge_to_cost_ratio"),
            }
        ),
    }


def build_short_research_row(
    row: dict[str, Any],
    *,
    campaign_root: Any,
) -> dict[str, Any] | None:
    enrichment = row.get("enrichment")
    regime_info = row.get("regime_info")
    if not isinstance(enrichment, dict) or not isinstance(regime_info, dict):
        return None
    regime_info = attach_regime_provenance(regime_info, enrichment=enrichment)
    structure = regime_info.get("market_structure") or "UNDETERMINED"
    regime = regime_info.get("regime") or "UNCERTAIN"
    edge = compute_expected_net_edge(enrichment=enrichment, side="SHORT", notional=NOTIONAL)
    entry_q = compute_entry_quality(
        enrichment, side="SHORT", structure=str(structure), regime=str(regime), edge=edge
    )
    support, contradict = build_evidence_lists(
        enrichment, side="SHORT", structure=str(structure), regime=str(regime), edge=edge
    )
    eq = float(entry_q.get("entry_quality_score") or 0)
    action, reason = _v2_abstention_action(
        entry_quality=eq,
        expected_net_edge=float(edge.get("expected_net_edge") or 0),
        edge_ratio=edge.get("edge_to_cost_ratio"),
        thesis_ok=True,
        gate_pass=bool(row.get("gate_pass", True)),
        contradict=contradict,
        direction="SHORT",
    )
    return {
        "symbol": row.get("symbol") or enrichment.get("symbol"),
        "direction": "SHORT",
        "entry_quality_score": eq,
        "expected_net_edge": edge.get("expected_net_edge"),
        "v2_action": action,
        "v2_reason": reason,
        "lane": "SHORT_SHADOW_RESEARCH",
        "supporting_evidence": support,
        "contradicting_evidence": contradict,
        "regime_provenance": {
            "engine_regime": regime_info.get("engine_regime"),
            "market_structure": regime_info.get("market_structure"),
            "mapping_version": regime_info.get("mapping_version"),
        },
        "detected_at_ms": int(enrichment.get("timestamp_ms") or 0),
        "price": enrichment.get("price"),
    }


def rank_by_score(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda c: float(c.get("entry_quality_score") or -999),
        reverse=True,
    )


def select_v2_c1_for_episode(
    ranked_rows: list[dict[str, Any]],
    *,
    campaign_root: Any,
    now_ms: int,
) -> dict[str, Any]:
    """One episode per cycle timestamp; LONG Top1 by score; SHORT research lane."""
    ep_id = episode_id_from_ms(now_ms)
    long_pool: list[dict[str, Any]] = []
    short_pool: list[dict[str, Any]] = []
    for row in ranked_rows:
        lc = build_long_candidate_row(row, campaign_root=campaign_root)
        if lc:
            long_pool.append(lc)
        sc = build_short_research_row(row, campaign_root=campaign_root)
        if sc:
            short_pool.append(sc)

    long_ranked = rank_by_score(long_pool)
    short_ranked = rank_by_score(short_pool)
    n_long = len(long_ranked)
    for i, c in enumerate(long_ranked, start=1):
        c["v2_rank"] = i
        c["rank_percentile"] = round((1.0 - (i - 1) / max(1, n_long)) * 100.0, 2)
        c["calibrated_probability"] = None
        c["calibration_status"] = "UNVALIDATED"
    for i, c in enumerate(short_ranked, start=1):
        c["v2_rank"] = i
        c["rank_percentile"] = round((1.0 - (i - 1) / max(1, len(short_ranked))) * 100.0, 2)

    long_top1 = long_ranked[0] if long_ranked else None
    short_top1 = short_ranked[0] if short_ranked else None

    # Edge percentiles (telemetry only — not used for C1 rank)
    edges = sorted(float(c.get("expected_net_edge") or -999) for c in long_pool + short_pool)
    for c in long_pool + short_pool:
        e = float(c.get("expected_net_edge") or -999)
        if not edges:
            c["expected_edge_percentile"] = None
        else:
            below = sum(1 for x in edges if x <= e)
            c["expected_edge_percentile"] = round(100.0 * below / len(edges), 2)

    return {
        "episode_id": ep_id,
        "episode_started_at_ms": ep_id * EPISODE_WINDOW_SEC * 1000,
        "episode_window_sec": EPISODE_WINDOW_SEC,
        "long_top1": long_top1,
        "short_research_top1": short_top1,
        "long_candidates_count": len(long_pool),
        "short_candidates_count": len(short_pool),
    }


def materialize_v2_evidence(
    selection: dict[str, Any],
    *,
    cycle_id: str,
    now_ms: int,
) -> list[dict[str, Any]]:
    """Build persistable evidence rows for LONG top1 + SHORT research."""
    out: list[dict[str, Any]] = []
    ep_id = selection.get("episode_id")

    def _pack(c: dict[str, Any] | None, *, lane: str) -> None:
        if not c:
            return
        v2_sid = f"v2sig_{uuid.uuid4().hex[:16]}"
        action = str(c.get("v2_action") or "WAIT")
        if lane == "SHORT_SHADOW_RESEARCH" and action == "READY":
            action = "WATCH"
            c = {**c, "v2_action": action, "v2_reason": "SHORT_READY_FORBIDDEN_C1"}
        selected_cohort = SELECTED_COHORT_NAME if lane == SELECTED_LANE else None
        action_cohort = ACTION_COHORT_READY if (lane == SELECTED_LANE and action == "READY") else None
        out.append(
            {
                "schema": "v30_v2_c1_challenger_evidence_v1",
                "champion_version": CHAMPION_VERSION,
                "challenger_version": CHALLENGER_VERSION,
                "evidence_generation": EVIDENCE_GENERATION,
                "historical_fit_note": HISTORICAL_FIT_NOTE,
                "cycle_id": cycle_id,
                "episode_id": ep_id,
                "episode_started_at_ms": selection.get("episode_started_at_ms"),
                "v2_signal_id": v2_sid,
                "signal_id": v2_sid,
                "symbol": c.get("symbol"),
                "direction": c.get("direction"),
                "detected_at_ms": c.get("detected_at_ms") or now_ms,
                "entry_price": c.get("price"),
                "score": c.get("entry_quality_score"),
                "raw_quality_score": c.get("raw_quality_score") or c.get("entry_quality_score"),
                "rank": c.get("v2_rank"),
                "rank_percentile": c.get("rank_percentile"),
                "calibrated_probability": None,
                "calibration_status": "UNVALIDATED",
                "action": action,
                "reason": c.get("v2_reason"),
                "lane": lane,
                "selected_cohort": selected_cohort,
                "action_cohort": action_cohort,
                "outcome_eligible": lane == SELECTED_LANE,
                "abstention_diagnostic": c.get("abstention_diagnostic"),
                "gate_pass": c.get("gate_pass"),
                "thesis_ok": c.get("thesis_ok"),
                "edge_to_cost_ratio": c.get("edge_to_cost_ratio"),
                "expected_net_edge": c.get("expected_net_edge"),
                "expected_edge_percentile": c.get("expected_edge_percentile"),
                "estimated_fee": c.get("estimated_fee") or estimate_round_trip_fee(NOTIONAL, fee_rate=FEE_RT),
                "estimated_spread": c.get("estimated_spread"),
                "estimated_slippage": c.get("estimated_slippage"),
                "estimated_funding": c.get("estimated_funding"),
                "estimated_total_cost": c.get("estimated_total_cost"),
                "cost_hurdle_research": c.get("cost_hurdle_research"),
                "fee_baseline_rt": FEE_RT,
                "supporting_evidence": c.get("supporting_evidence"),
                "contradicting_evidence": c.get("contradicting_evidence"),
                "critical_contradiction": c.get("critical_contradiction"),
                "regime_provenance": c.get("regime_provenance"),
                "v1_champion": c.get("v1_champion"),
                "primary_ranker": "SCORE",
                "LONG_top_k": 1,
                "no_hindsight": True,
            }
        )

    _pack(selection.get("long_top1"), lane=SELECTED_LANE)
    _pack(selection.get("short_research_top1"), lane="SHORT_SHADOW_RESEARCH")
    return out


def is_selected_top1_long(evidence: dict[str, Any]) -> bool:
    return (
        evidence.get("selected_cohort") == SELECTED_COHORT_NAME
        or evidence.get("lane") == SELECTED_LANE
    )
