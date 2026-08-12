"""Focused tests for Signal Quality V1 foundation."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from backend.nexus_research_ai_autonomy.anti_churn_thesis_v1 import evaluate_thesis_novelty, record_thesis
from backend.nexus_research_ai_autonomy.decision_snapshot_v30 import build_decision_snapshot
from backend.nexus_research_ai_autonomy.public_opportunity_dto_v1 import (
    build_public_opportunity_dto,
    dto_leaks_private_data,
)
from backend.nexus_research_ai_autonomy.shadow_signal_v1 import create_shadow_signal
from backend.nexus_research_ai_autonomy.signal_quality_v1 import (
    build_evidence_lists,
    classify_market_structure,
    compute_expected_net_edge,
    evaluate_regime,
)


def _enrichment(*, ts: int | None = None) -> dict[str, Any]:
    return {
        "symbol": "APRUSDT",
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


def test_decision_snapshot_no_future_timestamp() -> None:
    ts = int(time.time() * 1000)
    enrichment = _enrichment(ts=ts)
    regime = evaluate_regime(enrichment)
    edge = compute_expected_net_edge(enrichment=enrichment, side="LONG")
    from backend.nexus_research_ai_autonomy.signal_quality_v1 import compute_direction_scores, compute_entry_quality

    dirs = compute_direction_scores(enrichment, structure=regime["market_structure"], regime=regime["regime"])
    eq = compute_entry_quality(enrichment, side="LONG", structure=regime["market_structure"], regime=regime["regime"], edge=edge)
    support, contradict = build_evidence_lists(enrichment, side="LONG", structure=regime["market_structure"], regime=regime["regime"], edge=edge)
    snap = build_decision_snapshot(
        cycle_id="cyc_test",
        enrichment=enrichment,
        regime_info=regime,
        side="LONG",
        direction_scores=dirs,
        entry_quality=eq,
        edge=edge,
        supporting_evidence=support,
        contradicting_evidence=contradict,
        gate_results={"pass": True},
        final_action="WATCH",
        final_reason="test",
    )
    assert snap["timestamp_ms"] == ts
    assert snap["no_hindsight"] is True
    assert snap["timestamp_ms"] <= int(time.time() * 1000)


def test_activity_fallback_labeled() -> None:
    e = _enrichment()
    e["activity_source"] = "ACTIVITY_FALLBACK"
    e["activity_fallback"] = True
    e["activity_score"] = 0.2
    regime = evaluate_regime(e)
    edge = compute_expected_net_edge(enrichment=e, side="LONG")
    support, contradict = build_evidence_lists(e, side="LONG", structure=regime["market_structure"], regime=regime["regime"], edge=edge)
    assert "ACTIVITY_FALLBACK" in contradict


def test_dynamic_regime_not_silent_trend_up() -> None:
    e = _enrichment()
    e["momentum_5m"] = {"return": -0.25, "velocity": -0.1, "acceleration": -0.05}
    e["momentum_15m"] = {"return": -0.2, "velocity": -0.08, "acceleration": -0.03}
    structure = classify_market_structure(e)
    regime = evaluate_regime(e)
    assert structure in {"TREND_DOWN", "BREAKOUT_DOWN", "RANGE", "UNDETERMINED", "COMPRESSION"}
    assert regime["regime"] != "TREND_UP" or structure == "UNDETERMINED"


def test_expected_net_edge_includes_cost() -> None:
    edge = compute_expected_net_edge(enrichment=_enrichment(), side="LONG", notional=350.0)
    assert edge["estimated_round_trip_fee"] > 0
    assert edge["expected_net_edge"] == pytest.approx(
        edge["expected_gross_edge"]
        - edge["estimated_round_trip_fee"]
        - edge["estimated_spread_cost"]
        - edge["estimated_slippage_cost"]
        - edge["estimated_funding_cost"],
        rel=1e-6,
    )


def test_high_gross_negative_post_cost_ranks_lower() -> None:
    good = compute_expected_net_edge(enrichment=_enrichment(), side="LONG", notional=350.0, target_pct=0.55)
    bad = _enrichment()
    bad["spread_bps"] = 40.0
    bad["estimated_slippage"] = 0.05
    bad["funding_rate"] = 0.01
    poor = compute_expected_net_edge(enrichment=bad, side="LONG", notional=350.0, target_pct=0.55)
    assert poor["expected_net_edge"] < good["expected_net_edge"]


def test_supporting_and_contradicting_preserved() -> None:
    e = _enrichment()
    regime = evaluate_regime(e)
    edge = compute_expected_net_edge(enrichment=e, side="LONG")
    support, contradict = build_evidence_lists(e, side="LONG", structure=regime["market_structure"], regime=regime["regime"], edge=edge)
    assert isinstance(support, list)
    assert isinstance(contradict, list)
    assert len(support) + len(contradict) >= 1


def test_repeated_thesis_no_new_edge(tmp_path: Path) -> None:
    e = _enrichment()
    regime = evaluate_regime(e)
    edge = compute_expected_net_edge(enrichment=e, side="LONG")
    snap = {**e, **regime, **edge, "side": "LONG"}
    record_thesis(tmp_path, snap)
    out = evaluate_thesis_novelty(campaign_root=tmp_path, symbol="APRUSDT", side="LONG", current_snapshot=snap)
    assert out.get("pass") is False
    assert out.get("reason") == "REPEATED_THESIS_NO_NEW_EDGE"


def test_shadow_signal_lifecycle_deterministic() -> None:
    e = _enrichment()
    regime = evaluate_regime(e)
    edge = compute_expected_net_edge(enrichment=e, side="LONG")
    from backend.nexus_research_ai_autonomy.signal_quality_v1 import compute_direction_scores, compute_entry_quality

    dirs = compute_direction_scores(e, structure=regime["market_structure"], regime=regime["regime"])
    eq = compute_entry_quality(e, side="LONG", structure=regime["market_structure"], regime=regime["regime"], edge=edge)
    support, contradict = build_evidence_lists(e, side="LONG", structure=regime["market_structure"], regime=regime["regime"], edge=edge)
    snap = build_decision_snapshot(
        cycle_id="cyc_test",
        enrichment=e,
        regime_info=regime,
        side="LONG",
        direction_scores=dirs,
        entry_quality=eq,
        edge=edge,
        supporting_evidence=support,
        contradicting_evidence=contradict,
        gate_results={},
        final_action="SELECT",
        final_reason="READY",
    )
    sig = create_shadow_signal(snap)
    assert sig["lifecycle_state"] == "READY"
    assert sig["signal_id"].startswith("sig_")


def test_public_dto_no_private_leak() -> None:
    snap = {
        "symbol": "APRUSDT",
        "side": "LONG",
        "entry_quality_score": 0.7,
        "expected_net_edge": 0.5,
        "direction_confidence_quant": 0.65,
        "regime": "RANGE",
        "market_structure": "TREND_UP",
        "supporting_evidence": ["MOMENTUM_5M_POSITIVE"],
        "contradicting_evidence": [],
        "final_action": "WATCH",
        "data_freshness_ms": 10,
        "activity_source": "TURNOVER_LOG",
        "activity_fallback": False,
        "rank": 1,
        "rank_percentile": 99.0,
    }
    dto = build_public_opportunity_dto(snap)
    assert dto_leaks_private_data(dto) is False
    assert "api_secret" not in json.dumps(dto).lower()


def test_wait_remains_valid_action() -> None:
    e = _enrichment()
    e["spread_bps"] = 50.0
    edge = compute_expected_net_edge(enrichment=e, side="LONG")
    assert edge["expected_net_edge"] < edge["estimated_round_trip_fee"]


def test_shadow_path_mfe_mae_fixed_entry() -> None:
    from backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1 import evaluate_path_mfe_mae

    entry = 100.0
    # Path goes up then down — entry fixed at 100
    path = [
        (1_000, 100.2),
        (2_000, 100.6),  # +0.6% MFE
        (3_000, 99.5),   # -0.5%
    ]
    out = evaluate_path_mfe_mae(
        entry_price=entry,
        direction="LONG",
        path=path,
        stop_pct=0.40,
        target_pct=0.55,
        notional=350.0,
    )
    assert out["MFE"] is not None and out["MFE"] > 0
    assert out["MAE"] is not None and out["MAE"] < 0
    assert out["post_cost_hypothetical"] is not None
    # Cost must be subtracted
    assert out["estimated_cost"] > 0
    assert out["post_cost_hypothetical"] == pytest.approx(
        out["gross_hypothetical"] - out["estimated_cost"], rel=1e-6
    )


def test_shadow_target_before_stop_detectable() -> None:
    from backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1 import evaluate_path_mfe_mae

    path = [(1, 100.0), (2, 100.6)]  # +0.6% hits 0.55 target
    out = evaluate_path_mfe_mae(
        entry_price=100.0,
        direction="LONG",
        path=path,
        stop_pct=0.40,
        target_pct=0.55,
        notional=350.0,
    )
    assert out["target_before_stop"] is True
    assert out["stop_before_target"] is False


def test_counterfactual_does_not_auto_promote(tmp_path: Path) -> None:
    from backend.nexus_research_ai_autonomy.counterfactual_strategy_v1 import run_counterfactual_research

    bars = [
        {"ts_ms": 60_000, "open": 100.0, "high": 100.3, "low": 99.7, "close": 100.1, "entry_candle_partial": False},
        {"ts_ms": 120_000, "open": 100.1, "high": 100.8, "low": 100.0, "close": 100.5, "entry_candle_partial": False},
    ]
    records = [
        {"entry_price": 100.0, "direction": "LONG", "bars": bars, "notional": 350.0},
        {"entry_price": 100.0, "direction": "LONG", "bars": bars, "notional": 350.0},
    ]
    report = run_counterfactual_research(campaign_root=tmp_path, path_records=records)
    assert report["auto_promotion"] is False
    assert report["live_stop_pct_unchanged"] is True
    assert report["ready_for_demo_reenable"] is False
    assert all(c.get("auto_promoted") is False for c in report["research_configs"])
    assert len(report["research_configs"]) >= 3
    for c in report["research_configs"]:
        assert c["stats"]["sample_count"] == 2


def test_immature_horizon_not_evaluated(tmp_path: Path) -> None:
    """Horizons that have not elapsed must not fabricate outcomes."""
    from backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1 import evaluate_signal_horizons

    class _NoClient:
        def public_get(self, *_a, **_k):  # pragma: no cover
            raise AssertionError("should not fetch before horizon matures")

    now = int(time.time() * 1000)
    sig = {
        "signal_id": "sig_test",
        "symbol": "APRUSDT",
        "direction": "LONG",
        "entry_price": 1.0,
        "detected_at_ms": now,  # just created — no horizon mature
    }
    rows = evaluate_signal_horizons(_NoClient(), signal=sig, campaign_root=tmp_path, horizons=(60, 180))
    assert rows == []
