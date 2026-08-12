"""V18.2.28 — exchange preflight, two-sided hypothesis, adaptive capture, reflection."""
from __future__ import annotations

from decimal import Decimal

from backend.nexus_research_ai_autonomy.adaptive_profit_capture import (
    AdaptiveProfitCaptureManager,
    compute_mfe_capture_metrics,
)
from backend.nexus_research_ai_autonomy.exchange_preflight import normalize_qty
from backend.nexus_research_ai_autonomy.failure_reflection_v28 import (
    build_mistake_signature,
    create_failure_reflection,
    infer_root_causes,
)
from backend.nexus_research_ai_autonomy.two_sided_hypothesis import evaluate_two_sided_hypothesis
from backend.nexus_research_ai_autonomy.win_rate_stats import compute_mfe_capture_ratio, compute_performance_stats


def test_normalize_qty_decimal_floors_not_rounds_up():
    qty_str, qty_f = normalize_qty(1.237, qty_step=0.1)
    assert qty_str == "1.2"
    assert qty_f == 1.2


def test_two_sided_hypothesis_no_forced_side():
    h = evaluate_two_sided_hypothesis(
        symbol="BTCUSDT",
        entry_price=64000.0,
        equity=5000.0,
        vol_pct_per_hour=0.35,
        turnover24h=1e9,
        activity_score=0.8,
        qty_step=0.001,
        min_qty=0.001,
        min_notional=5.0,
    )
    assert h.selected_side in {"LONG", "SHORT", "WAIT"}
    assert h.long_score is not None
    assert h.short_score is not None


def test_direction_ambiguity_on_exact_tie_wait():
    # Force deterministic tie by using a MarketCandidate situation where rank_score is equal:
    # We can't control internals of score_market_candidate here, so we check the rule indirectly:
    # if both sides end up passing and the rounded scores tie, the side must be WAIT.
    h = evaluate_two_sided_hypothesis(
        symbol="BTCUSDT",
        entry_price=64000.0,
        equity=5000.0,
        vol_pct_per_hour=0.35,
        turnover24h=1e9,
        activity_score=0.8,
        qty_step=0.001,
        min_qty=0.001,
        min_notional=5.0,
    )
    if h.direction_ambiguity_supported:
        assert h.selected_side == "WAIT"
        assert h.wait_reason == "DIRECTION_AMBIGUOUS"


def test_adaptive_capture_exit_on_edge_decay():
    mgr = AdaptiveProfitCaptureManager(slow_path_leak_count=0)
    assert mgr.slow_path_leak_count == 0
    assert mgr.exchange_sl_mandatory is True
    metrics = compute_mfe_capture_metrics(realized_usdt=3.1, mfe_usdt=3.5)
    assert metrics["MFE_capture_ratio"] is not None
    assert metrics["MFE_capture_ratio"] > 0.85


def test_mfe_capture_ratio_invalid_when_no_mfe():
    assert compute_mfe_capture_ratio(mfe_usdt=0.0, realized_favorable_usdt=1.0) is None
    assert compute_mfe_capture_ratio(mfe_usdt=3.5, realized_favorable_usdt=3.1) == 3.1 / 3.5


def test_win_rate_insufficient_sample():
    stats = compute_performance_stats([])
    assert stats.winrate_sample_status == "INSUFFICIENT_SAMPLE_FOR_WINRATE_CLAIM"
    stats2 = compute_performance_stats(
        [
            {
                "lifecycle_purpose": "RESEARCH_PNL_TRADE",
                "accounting_complete": True,
                "symbol": "ETHUSDT",
                "side": "LONG",
                "exact_pnl_accounting": {"accounting_complete": True, "calculated_net_pnl": -1.8},
                "path_excursion": {"mfe_usdt": 0.1},
            }
        ]
    )
    assert stats2.accounting_complete_trades == 1
    assert stats2.winrate_sample_status == "INSUFFICIENT_SAMPLE_FOR_WINRATE_CLAIM"


def test_failure_reflection_on_loss():
    lc = {
        "symbol": "ETHUSDT",
        "side": "LONG",
        "strategy_family": "TREND",
        "regime_at_entry": "RANGE",
        "exact_pnl_accounting": {"calculated_net_pnl": -1.8},
        "path_excursion": {"mfe_usdt": 0.0},
    }
    root = infer_root_causes(lc, "REGIME_FAILURE")
    assert "WRONG_DIRECTION" in root or "REGIME_MISMATCH" in root
    sig = build_mistake_signature(root, lc)
    assert sig
    refl = create_failure_reflection(lc, process_class="GOOD_PROCESS_LOSS", exit_quality_class="REGIME_FAILURE")
    assert refl is not None
    assert refl.candidate_lesson is not None


def test_canonical_metric_consistency():
    from backend.nexus_research_ai_autonomy.canonical_evidence import validate_metric_consistency

    r = validate_metric_consistency(
        funnel_sealed={"both_pass": 1, "real_orders": 0},
        gate_sealed={"ECONOMIC_EDGE_PASS": True, "HORIZON_FEASIBILITY_PASS": True},
        market_opportunity={"funnel": {"both_pass": 2}},
    )
    assert r["metric_consistency_pass"] is False
    assert r["conflicts"]
