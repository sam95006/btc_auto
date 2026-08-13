"""P0.5 focused tests — V2-C1 selected vs READY cohort semantics."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from backend.nexus_research_ai_autonomy.shadow_signal_v1 import load_signal_state
from backend.nexus_research_ai_autonomy.shadow_v2_challenger_v1 import (
    EVIDENCE_GENERATION,
    build_shadow_v2_challenger_report,
    count_duplicate_long_top1_episodes,
    count_duplicate_long_top1_episodes,
    evidence_to_shadow_signal,
    load_v2_c1_shadow_signals,
    persist_v2_evidence,
    run_v2_c1_shadow_challenger,
)
from backend.nexus_research_ai_autonomy.signal_quality_v2_c1 import (
    ACTION_COHORT_READY,
    CHALLENGER_VERSION,
    SELECTED_COHORT_NAME,
    SELECTED_LANE,
    audit_ready_threshold_provenance,
    classify_abstention_diagnostic,
    materialize_v2_evidence,
    select_v2_c1_for_episode,
)


def _enrichment(*, sym: str = "APRUSDT", ts: int | None = None) -> dict[str, Any]:
    return {
        "symbol": sym,
        "timestamp_ms": ts or int(time.time() * 1000),
        "price": 1.0,
        "turnover": 20_000_000,
        "spread_bps": 3.0,
        "estimated_slippage": 0.0003,
        "activity_score": 0.72,
        "activity_source": "TURNOVER_LOG",
        "activity_fallback": False,
        "momentum_1m": {"return": 0.05, "velocity": 0.02, "acceleration": 0.01},
        "momentum_5m": {"return": 0.12, "velocity": 0.04, "acceleration": 0.02},
        "momentum_15m": {"return": 0.08, "velocity": 0.03, "acceleration": 0.01},
        "volatility": 0.35,
        "open_interest": 1000.0,
        "oi_delta_short": 0.02,
        "funding_rate": 0.0001,
        "data_freshness_ms": 50,
    }


def _regime_info() -> dict[str, Any]:
    return {"market_structure": "TREND_UP", "regime": "TREND_UP", "regime_confidence": 0.7}


def _ranked_row(*, sym: str, ts: int, gate_pass: bool = True) -> dict[str, Any]:
    from backend.nexus_research_ai_autonomy.signal_quality_v1 import (
        build_evidence_lists,
        compute_entry_quality,
        compute_expected_net_edge,
    )

    enrichment = _enrichment(sym=sym, ts=ts)
    regime_info = _regime_info()
    edge = compute_expected_net_edge(enrichment=enrichment, side="LONG", notional=350.0)
    eq = compute_entry_quality(
        enrichment, side="LONG", structure="TREND_UP", regime="TREND_UP", edge=edge
    )
    support, contradict = build_evidence_lists(
        enrichment, side="LONG", structure="TREND_UP", regime="TREND_UP", edge=edge
    )
    return {
        "symbol": sym,
        "side": "LONG",
        "entry_quality_score": eq.get("entry_quality_score"),
        "expected_net_edge": edge.get("expected_net_edge"),
        "snapshot": {
            "final_action": "WATCH",
            "rank": 1,
            "entry_quality_score": eq.get("entry_quality_score"),
            "expected_net_edge": edge.get("expected_net_edge"),
            "supporting_evidence": support,
            "contradicting_evidence": contradict,
        },
        "enrichment": enrichment,
        "regime_info": regime_info,
        "gate_pass": gate_pass,
        "timestamp_ms": ts,
    }


def test_every_episode_at_most_one_selected_long_top1(tmp_path: Path) -> None:
    ts = int(time.time() * 1000)
    rows = [_ranked_row(sym="AUSDT", ts=ts), _ranked_row(sym="BUSDT", ts=ts)]
    run_v2_c1_shadow_challenger(campaign_root=tmp_path, cycle_id="cyc1", now_ms=ts, ranked_rows=rows)
    # Same episode window — second cycle must not duplicate selected Top1
    run_v2_c1_shadow_challenger(
        campaign_root=tmp_path, cycle_id="cyc2", now_ms=ts + 1000, ranked_rows=rows
    )
    selected = [e for e in load_v2_c1_shadow_signals(tmp_path) if e.get("selected_cohort")]
    assert len(selected) == 1
    assert count_duplicate_long_top1_episodes(tmp_path) == 0


def test_selected_top1_persists_when_wait_watch_block(tmp_path: Path) -> None:
    ts = int(time.time() * 1000)
    row = _ranked_row(sym="APRUSDT", ts=ts, gate_pass=False)
    run_v2_c1_shadow_challenger(campaign_root=tmp_path, cycle_id="cyc", now_ms=ts, ranked_rows=[row])
    selected = [e for e in load_v2_c1_shadow_signals(tmp_path) if e.get("selected_cohort")]
    assert len(selected) == 1
    assert selected[0]["action"] in {"WAIT", "BLOCK", "WATCH"}
    assert selected[0]["selected_cohort"] == SELECTED_COHORT_NAME
    assert selected[0].get("action_cohort") is None


def test_selected_top1_outcomes_lifecycle_registered(tmp_path: Path) -> None:
    ts = int(time.time() * 1000)
    rows = [_ranked_row(sym="APRUSDT", ts=ts, gate_pass=False)]
    run_v2_c1_shadow_challenger(campaign_root=tmp_path, cycle_id="cyc", now_ms=ts, ranked_rows=rows)
    v2 = load_v2_c1_shadow_signals(tmp_path)
    selected = next(e for e in v2 if e.get("selected_cohort"))
    sig = evidence_to_shadow_signal(selected)
    assert sig.get("outcome_eligible") is True
    state = load_signal_state(tmp_path)
    ent = (state.get("signals") or {}).get(str(selected["signal_id"]))
    assert ent is not None
    assert set((ent.get("horizon_status") or {}).keys()) == {"1m", "3m", "5m", "15m", "30m"}


def test_selected_cohort_report_does_not_filter_action(tmp_path: Path) -> None:
    ts = int(time.time() * 1000)
    run_v2_c1_shadow_challenger(
        campaign_root=tmp_path,
        cycle_id="cyc",
        now_ms=ts,
        ranked_rows=[_ranked_row(sym="APRUSDT", ts=ts, gate_pass=False)],
    )
    report = build_shadow_v2_challenger_report(tmp_path)
    assert report["selected_top1_long_count"] == 1
    assert report["v2_ready"] == 0
    assert report["selected_top1_action_distribution"]
    assert "selected_top1_horizons" in report
    assert report["primary_validation_counter"] == "SELECTED_TOP1_LONG"


def test_ready_cohort_filters_ready_only(tmp_path: Path) -> None:
    ts = int(time.time() * 1000)
    sel1 = select_v2_c1_for_episode(
        [_ranked_row(sym="APRUSDT", ts=ts, gate_pass=False)],
        campaign_root=tmp_path,
        now_ms=ts,
    )
    evidence1 = materialize_v2_evidence(sel1, cycle_id="cyc1", now_ms=ts)
    long_ev = next(e for e in evidence1 if e.get("selected_cohort"))
    long_ev_ready = {**long_ev, "action": "READY", "action_cohort": ACTION_COHORT_READY}
    ts2 = ts + 120_000
    sel2 = select_v2_c1_for_episode(
        [_ranked_row(sym="BUSDT", ts=ts2, gate_pass=False)],
        campaign_root=tmp_path,
        now_ms=ts2,
    )
    evidence2 = materialize_v2_evidence(sel2, cycle_id="cyc2", now_ms=ts2)
    long_ev_wait = next(e for e in evidence2 if e.get("selected_cohort"))
    persist_v2_evidence(tmp_path, [long_ev_ready, long_ev_wait])
    report = build_shadow_v2_challenger_report(tmp_path)
    assert report["selected_top1_long_count"] == 2
    assert report["v2_ready"] == 1


def test_selected_and_ready_metrics_not_conflated(tmp_path: Path) -> None:
    report = build_shadow_v2_challenger_report(Path("/nonexistent"))
    assert report["selected_cohort_name"] == SELECTED_COHORT_NAME
    assert report["ready_validation_counter"] == "SEPARATE"
    assert "selected_top1_horizons" in report
    assert "ready_horizons" in report
    gates = report["validation_gates"]
    assert "selected_top1_long" in gates
    assert "v2_ready" in gates


def test_post_v2_freeze_only(tmp_path: Path) -> None:
    ts = int(time.time() * 1000)
    run_v2_c1_shadow_challenger(
        campaign_root=tmp_path, cycle_id="cyc", now_ms=ts, ranked_rows=[_ranked_row(sym="X", ts=ts)]
    )
    for row in load_v2_c1_shadow_signals(tmp_path):
        assert row.get("evidence_generation") == EVIDENCE_GENERATION
        assert row.get("challenger_version") == CHALLENGER_VERSION


def test_no_future_outcome_in_selection() -> None:
    ts = int(time.time() * 1000)
    sel = select_v2_c1_for_episode(
        [_ranked_row(sym="APRUSDT", ts=ts)], campaign_root=Path("/tmp/x"), now_ms=ts
    )
    evidence = materialize_v2_evidence(sel, cycle_id="cyc", now_ms=ts)
    banned = {"MFE", "MAE", "post_cost_hypothetical", "target_before_stop"}
    for ev in evidence:
        assert ev.get("no_hindsight") is True
        assert banned.isdisjoint(ev.keys())


def test_short_never_ready() -> None:
    ts = int(time.time() * 1000)
    sel = select_v2_c1_for_episode([_ranked_row(sym="APRUSDT", ts=ts)], campaign_root=Path("/tmp/x"), now_ms=ts)
    evidence = materialize_v2_evidence(sel, cycle_id="cyc", now_ms=ts)
    short = next(e for e in evidence if e.get("lane") == "SHORT_SHADOW_RESEARCH")
    assert short["action"] != "READY"


def test_demo_write_false() -> None:
    report = build_shadow_v2_challenger_report(Path("/nonexistent"))
    assert report.get("ready_for_demo_reenable") is False
    assert report.get("promotion_auto_enable") is False


def test_threshold_provenance_inherited_from_v1() -> None:
    prov = audit_ready_threshold_provenance()
    assert prov["entry_quality_065"]["provenance"] == "INHERITED_EXISTING_GATE"
    assert prov["watch_050"]["provenance"] == "INHERITED_EXISTING_GATE"
    assert prov["edge_ratio_120"]["provenance"] == "INHERITED_EXISTING_GATE"
    assert prov["entry_quality_065"]["part_of_frozen_c1_selection"] is False


def test_abstention_diagnostic_buckets() -> None:
    assert classify_abstention_diagnostic({"v2_action": "READY"}) == "ready"
    assert (
        classify_abstention_diagnostic(
            {
                "v2_action": "WAIT",
                "gate_pass": False,
                "thesis_ok": True,
                "v2_reason": "GATES_NOT_PASSED",
            }
        )
        == "gate_not_passed"
    )
    assert (
        classify_abstention_diagnostic(
            {
                "v2_action": "WAIT",
                "thesis_ok": True,
                "gate_pass": True,
                "v2_reason": "INSUFFICIENT_ENTRY_QUALITY",
                "entry_quality_score": 0.3,
                "expected_net_edge": 0.05,
            }
        )
        == "entry_quality_threshold"
    )
