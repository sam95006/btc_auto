"""Signal Quality shadow cycle — read-only, no Demo writes."""
from __future__ import annotations

import time
import uuid
from typing import Any

from backend.nexus_demo_execution.demo_write_client import DemoWriteClient
from backend.nexus_research_ai_autonomy.anti_churn_thesis_v1 import evaluate_thesis_novelty, record_thesis
from backend.nexus_research_ai_autonomy.cloud_paths_v301 import campaign_root
from backend.nexus_research_ai_autonomy.decision_snapshot_v30 import (
    build_decision_snapshot,
    persist_cycle_snapshots,
)
from backend.nexus_research_ai_autonomy.public_opportunity_dto_v1 import build_public_opportunity_dto
from backend.nexus_research_ai_autonomy.shadow_signal_v1 import create_shadow_signal, persist_shadow_signals
from backend.nexus_research_ai_autonomy.signal_enrichment_v1 import enrich_symbol
from backend.nexus_research_ai_autonomy.signal_quality_v1 import (
    build_evidence_lists,
    compute_direction_scores,
    compute_entry_quality,
    compute_expected_net_edge,
    evaluate_regime,
)


def _action_from_scores(
    *,
    side: str,
    entry_quality: float,
    expected_net_edge: float,
    edge_ratio: float | None,
    thesis_ok: bool,
    gate_pass: bool,
) -> tuple[str, str]:
    if not thesis_ok:
        return "BLOCK", "REPEATED_THESIS_NO_NEW_EDGE"
    if not gate_pass:
        return "WAIT", "GATES_NOT_PASSED"
    if expected_net_edge <= 0:
        return "WAIT", "POST_COST_EDGE_NEGATIVE"
    if entry_quality >= 0.65 and expected_net_edge > 0 and (edge_ratio or 0) >= 1.2:
        return "SELECT", "READY_POST_COST_EDGE"
    if entry_quality >= 0.5 and expected_net_edge > 0:
        return "WATCH", "WATCH_QUALIFIED"
    return "WAIT", "INSUFFICIENT_ENTRY_QUALITY"


def run_signal_quality_shadow_cycle(
    *,
    client: DemoWriteClient,
    market_pack: dict[str, Any],
    equity: float = 5000.0,
    campaign_root_path=None,
) -> dict[str, Any]:
    """Enrich scan results, rank cross-sectionally, persist snapshots + shadow signals."""
    croot = campaign_root_path or campaign_root()
    cycle_id = f"cyc_{uuid.uuid4().hex[:12]}"
    now_ms = int(time.time() * 1000)
    tickers = market_pack.get("tickers") or []
    if not tickers:
        # rebuild from hypotheses sample if needed
        hyps = market_pack.get("hypotheses_sample") or []
        tickers = [{"symbol": h.get("symbol"), "last_price": (h.get("long_candidate") or {}).get("entry_price")} for h in hyps]

    ranked_rows: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    shadow_signals: list[dict[str, Any]] = []
    public_dtos: list[dict[str, Any]] = []

    for t in tickers:
        sym = str(t.get("symbol") or "")
        if not sym:
            continue
        enrichment = enrich_symbol(client, symbol=sym, ticker_row=t, now_ms=now_ms)
        regime_info = evaluate_regime(enrichment)
        structure = regime_info.get("market_structure") or "UNDETERMINED"
        regime = regime_info.get("regime") or "UNCERTAIN"
        direction_scores = compute_direction_scores(enrichment, structure=structure, regime=regime)
        best_side = "LONG" if direction_scores["LONG"] >= direction_scores["SHORT"] else "SHORT"
        edge = compute_expected_net_edge(enrichment=enrichment, side=best_side, notional=350.0)
        entry_q = compute_entry_quality(enrichment, side=best_side, structure=structure, regime=regime, edge=edge)
        support, contradict = build_evidence_lists(
            enrichment, side=best_side, structure=structure, regime=regime, edge=edge
        )
        # Match legacy gate info from market pack hypotheses if present
        gate_pass = True
        h_match = next((h for h in (market_pack.get("hypotheses_sample") or []) if h.get("symbol") == sym), None)
        if h_match:
            sel = h_match.get("selected_side")
            cand = h_match.get("long_candidate") if sel == "LONG" else h_match.get("short_candidate")
            if cand:
                gate_pass = bool(
                    cand.get("economic_edge_pass")
                    and cand.get("horizon_feasibility_pass")
                    and cand.get("risk_pass")
                )
        thesis = evaluate_thesis_novelty(
            campaign_root=croot,
            symbol=sym,
            side=best_side,
            current_snapshot={**enrichment, **regime_info, **edge, "side": best_side},
        )
        action, reason = _action_from_scores(
            side=best_side,
            entry_quality=float(entry_q.get("entry_quality_score") or 0),
            expected_net_edge=float(edge.get("expected_net_edge") or 0),
            edge_ratio=edge.get("edge_to_cost_ratio"),
            thesis_ok=bool(thesis.get("pass")),
            gate_pass=gate_pass,
        )
        snap = build_decision_snapshot(
            cycle_id=cycle_id,
            enrichment=enrichment,
            regime_info=regime_info,
            side=best_side,
            direction_scores=direction_scores,
            entry_quality=entry_q,
            edge=edge,
            supporting_evidence=support,
            contradicting_evidence=contradict + ([] if thesis.get("pass") else ["REPEATED_THESIS_NO_NEW_EDGE"]),
            gate_results={"legacy_gates_pass": gate_pass, "thesis_novelty": thesis},
            final_action=action,
            final_reason=reason if thesis.get("pass") else str(thesis.get("reason")),
            risk_flags=contradict[:5],
        )
        ranked_rows.append(
            {
                "symbol": sym,
                "side": best_side,
                "entry_quality_score": entry_q.get("entry_quality_score"),
                "expected_net_edge": edge.get("expected_net_edge"),
                "edge_to_cost_ratio": edge.get("edge_to_cost_ratio"),
                "long_score": direction_scores["LONG"],
                "short_score": direction_scores["SHORT"],
                "final_action": action,
                "snapshot": snap,
            }
        )

    ranked_rows.sort(
        key=lambda r: (float(r.get("expected_net_edge") or -999), float(r.get("entry_quality_score") or 0)),
        reverse=True,
    )
    n = len(ranked_rows)
    for i, row in enumerate(ranked_rows, start=1):
        snap = row["snapshot"]
        snap["rank"] = i
        snap["rank_percentile"] = round((1.0 - (i - 1) / max(1, n)) * 100.0, 2)
        snapshots.append(snap)
        if snap.get("final_action") in {"SELECT", "WATCH"}:
            sig = create_shadow_signal(snap)
            shadow_signals.append(sig)
            public_dtos.append(build_public_opportunity_dto(snap, signal=sig))
        if snap.get("final_action") == "SELECT":
            record_thesis(croot, snap)

    if snapshots:
        persist_cycle_snapshots(croot, cycle_id, snapshots)
    if shadow_signals:
        persist_shadow_signals(croot, shadow_signals)

    top = ranked_rows[0] if ranked_rows else None
    return {
        "schema": "v30_signal_quality_shadow_cycle_v1",
        "cycle_id": cycle_id,
        "timestamp_ms": now_ms,
        "candidates_enriched": len(ranked_rows),
        "snapshots_persisted": len(snapshots),
        "shadow_signals_created": len(shadow_signals),
        "top_candidate": {
            "symbol": top.get("symbol") if top else None,
            "side": top.get("side") if top else None,
            "expected_net_edge": top.get("expected_net_edge") if top else None,
            "entry_quality_score": top.get("entry_quality_score") if top else None,
            "final_action": top.get("final_action") if top else "WAIT",
        }
        if top
        else None,
        "ranking": [
            {
                "rank": i + 1,
                "symbol": r["symbol"],
                "side": r["side"],
                "expected_net_edge": r.get("expected_net_edge"),
                "entry_quality_score": r.get("entry_quality_score"),
                "final_action": r.get("final_action"),
            }
            for i, r in enumerate(ranked_rows[:10])
        ],
        "public_opportunities": public_dtos[:5],
        "write_paused": True,
    }
