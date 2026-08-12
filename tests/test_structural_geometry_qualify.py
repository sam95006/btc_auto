"""Structural Geometry offline qualification tests — no live arming."""
from __future__ import annotations

from backend.nexus_demo_execution.geometry_qualification_pipeline import run_qualification_pipeline
from backend.nexus_demo_execution.session_limits import MIN_NET_REWARD_RISK_RATIO, MIN_NET_REWARD_TO_COST
from backend.nexus_demo_execution.structural_geometry_qualify import (
    CandidateEvidence,
    compare_ab,
    evaluate_fixed_geometry,
    evaluate_structural_geometry,
    synthesize_structure_candidates,
)


def test_floors_unchanged():
    assert MIN_NET_REWARD_RISK_RATIO == 1.2
    assert MIN_NET_REWARD_TO_COST == 1.5


def test_fixed_geometry_zero_pass_on_symmetric():
    c = CandidateEvidence(
        symbol="BTCUSDT",
        side="Buy",
        entry_price=100.0,
        qty=5.0,
        fee_rate=0.00055,
        spread_bps=2.0,
        slippage_bps=2.0,
    )
    fixed = evaluate_fixed_geometry(c)
    assert fixed["gross_rr"] == 1.0
    assert fixed["cost_gate_pass"] is False


def test_missing_structure_inputs_block():
    c = CandidateEvidence(symbol="ETHUSDT", side="Buy", entry_price=2000.0, fee_rate=0.00055)
    s = evaluate_structural_geometry(c)
    assert s["geometry_missing"] is True
    assert s["block_reason"] == "GEOMETRY_INPUT_MISSING"
    assert s["cost_gate_pass"] is False


def test_stale_geometry():
    c = CandidateEvidence(
        symbol="ETHUSDT",
        side="Buy",
        entry_price=2000.0,
        atr=20.0,
        recent_swing_high=2100.0,
        recent_swing_low=1950.0,
        support=1940.0,
        resistance=2080.0,
        fee_rate=0.00055,
        data_freshness_sec=9999,
        max_freshness_sec=300,
    )
    s = evaluate_structural_geometry(c)
    assert s["block_reason"] == "GEOMETRY_STALE"


def test_ab_replay_diagnostic_only():
    cands = synthesize_structure_candidates(200)
    ab = compare_ab(cands)
    assert ab["diagnostic_only"] is True
    assert ab["oos_claim_forbidden"] is True
    assert ab["fixed_geometry_pass_rate"] == 0.0
    # Structural may pass some — but synthetic mix must not be artificial 100%.
    assert 0.0 < ab["structural_geometry_pass_rate"] < 1.0
    assert ab["structural_geometry_missing"] > 0
    assert ab["structural_geometry_invalid"] > 0


def test_qualification_pipeline_not_complete_without_risk_shadow():
    report = run_qualification_pipeline(synthesize_structure_candidates(40))
    assert report["fixed_geometry_retired_from_qualification"] is True
    assert report["active_execution_policy_unchanged"] is True
    assert report["qualification_complete"] is False
    assert report["recommendation"] == "NEXUS_GEOMETRY_QUALIFICATION_IN_PROGRESS"
    assert report["stages"]["SHADOW_APPLIED"]["status"] == "NOT_APPLIED"
