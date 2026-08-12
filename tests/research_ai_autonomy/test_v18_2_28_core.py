# -*- coding: utf-8 -*-
"""V18.2.28 — canonical evidence, metric consistency, win rate, long/short."""
from backend.nexus_research_ai_autonomy.canonical_evidence import (
    apply_sealed_to_time_basis,
    seal_funnel_metrics,
    seal_gate_metrics,
    validate_metric_consistency,
)
from backend.nexus_research_ai_autonomy.long_short_symmetry import evaluate_symbol_sides
from backend.nexus_research_ai_autonomy.win_rate_accounting import (
    INSUFFICIENT_SAMPLE_FOR_WINRATE_CLAIM,
    compute_research_win_rate,
)


def test_seal_funnel_metrics_single_source():
    funnel = {"eligible": 47, "economic_edge_pass": 13, "horizon_feasibility_pass": 1}
    sealed = seal_funnel_metrics(funnel=funnel, selected={"symbol": "BTCUSDT", "economic_edge_pass": True})
    assert sealed["eligible"] == 47
    assert sealed["economic_edge_pass"] == 13
    assert sealed["intermediate_override_blocked"] is True


def test_metric_consistency_pass_when_mirrored():
    funnel_sealed = seal_funnel_metrics(funnel={"eligible": 10, "economic_edge_pass": 3})
    gate_sealed = seal_gate_metrics(pnl_pack={"ECONOMIC_EDGE_PASS": True, "HORIZON_FEASIBILITY_PASS": True})
    tb = apply_sealed_to_time_basis({}, gate_sealed=gate_sealed, funnel_sealed=funnel_sealed)
    mc = validate_metric_consistency(
        funnel_sealed=funnel_sealed,
        gate_sealed=gate_sealed,
        time_basis=tb,
        market_opportunity={"funnel": {"eligible": 10, "economic_edge_pass": 3}},
        session_pnl_pack={"ECONOMIC_EDGE_PASS": True, "HORIZON_FEASIBILITY_PASS": True},
    )
    assert mc["metric_consistency_pass"] is True


def test_metric_consistency_fail_on_intermediate_null():
    funnel_sealed = seal_funnel_metrics(funnel={"eligible": 10})
    gate_sealed = seal_gate_metrics(
        pnl_pack={"ECONOMIC_EDGE_PASS": True},
        selected={"economic_edge_pass": True, "horizon_feasibility_pass": True},
    )
    tb = {"ECONOMIC_EDGE_PASS": None, "HORIZON_FEASIBILITY_PASS": None}
    mc = validate_metric_consistency(
        funnel_sealed=funnel_sealed,
        gate_sealed=gate_sealed,
        time_basis=tb,
    )
    assert mc["metric_consistency_pass"] is False
    assert any(c.get("kind") == "intermediate_null_override" for c in mc["conflicts"])


def test_long_short_symmetry_scores():
    ev = evaluate_symbol_sides(
        symbol="BTCUSDT",
        entry_price=64000.0,
        equity=5000.0,
        vol_pct_per_hour=0.35,
        turnover24h=50_000_000.0,
        change_pct_24h=1.2,
    )
    assert "long_score" in ev
    assert "short_score" in ev
    assert ev["selected_side"] in {"LONG", "SHORT", "WAIT"}
    assert ev["symmetry_evaluated"] is True


def test_win_rate_insufficient_sample():
    wr = compute_research_win_rate(
        [
            {
                "lifecycle_purpose": "RESEARCH_PNL_TRADE",
                "wallet_reconciliation": {"WALLET_RECONCILIATION_PASS": True, "actual_wallet_delta": -1.0},
                "side": "LONG",
            }
        ]
    )
    assert wr["n"] == 1
    assert wr["win_rate"] is None
    assert wr["win_rate_claim_status"] == INSUFFICIENT_SAMPLE_FOR_WINRATE_CLAIM


def test_win_rate_long_short_split():
    lives = [
        {
            "lifecycle_purpose": "RESEARCH_PNL_TRADE",
            "wallet_reconciliation": {"WALLET_RECONCILIATION_PASS": True, "actual_wallet_delta": 2.0},
            "side": "LONG",
        },
        {
            "lifecycle_purpose": "RESEARCH_PNL_TRADE",
            "wallet_reconciliation": {"WALLET_RECONCILIATION_PASS": True, "actual_wallet_delta": -1.0},
            "side": "SHORT",
        },
    ]
    wr = compute_research_win_rate(lives)
    assert wr["long_performance"]["n"] == 1
    assert wr["short_performance"]["n"] == 1
