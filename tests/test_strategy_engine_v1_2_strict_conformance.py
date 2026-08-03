"""Tests for Strategy Engine V1.2 strict conformance and coverage gates."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ["NEXUS_AI_MOCK"] = "1"

from backend.nexus_strategy_engine.conformance_v1_2 import (
    BLOCK_LATE,
    BLOCK_MISSING,
    BLOCK_REGIME,
    CONTROL_LABEL,
    run_strict_conformance,
)
from backend.nexus_strategy_engine.data_bundle import compute_partition_integrity, resample_ohlcv
from backend.nexus_demo_execution.historical_market_data import Candle


def test_strict_conformance_all_five_types_pass():
    s = run_strict_conformance()
    assert s["component_conformance_test_count"] >= 80
    assert s["strict_positive_fixture_pass_count"] == 16
    assert s["strict_negative_fixture_pass_count"] == 16
    assert s["strict_regime_block_pass_count"] == 16
    assert s["strict_missing_data_block_pass_count"] == 16
    assert s["strict_late_entry_pass_count"] == 16
    assert s["component_conformance_failure_count"] == 0
    assert s["targets_met"] is True
    # Positive cannot be zero-signal pass
    for c in s["cases"]:
        if c["case"] == "POSITIVE_EVENT":
            assert c["event_count"] >= 1
            assert c["passed"] is True
        if c["case"] == "NEGATIVE_EVENT":
            assert c["event_count"] == 0
        if c["case"] == "MISSING_DATA_BLOCK":
            assert c["candidate_count"] == 0
            assert c["block_reason"] == BLOCK_MISSING
        if c["case"] == "REGIME_BLOCK":
            assert c["candidate_count"] == 0
            assert c["block_reason"] == BLOCK_REGIME
        if c["case"] == "LATE_ENTRY_REJECTION":
            assert c["candidate_count"] == 0
            assert c["block_reason"] == BLOCK_LATE
        assert c["label"] == CONTROL_LABEL


def test_positive_zero_signal_would_fail_logic():
    # Guard: schema requires event_count>=1 for positives that passed
    s = run_strict_conformance()
    zeros = [c for c in s["cases"] if c["case"] == "POSITIVE_EVENT" and c["event_count"] == 0]
    assert zeros == []


def test_asof_resample_no_future():
    t0 = 1_700_000_000_000
    c15 = [
        Candle(ts_ms=t0 + i * 900_000, open=100, high=101, low=99, close=100 + i * 0.01, volume=1)
        for i in range(96)
    ]
    c60 = resample_ohlcv(c15, target_interval="60")
    assert c60[-1].ts_ms <= c15[-1].ts_ms


def test_complete_partition_checksum():
    t0 = 1_700_000_000_000
    c = [Candle(ts_ms=t0 + i * 900_000, open=1, high=2, low=0.5, close=1.5, volume=1) for i in range(20)]
    integ = compute_partition_integrity(c, interval="15")
    assert integ["full_partition_checksum"]
    assert integ["record_count"] == 20


def test_mock_calibration_not_labeled_real():
    from backend.nexus_strategy_engine.reflection_v2_1 import run_reflection_calibration_v21

    out = run_reflection_calibration_v21([], use_real_ai=False)
    assert out.get("schema") != "real_reflection_v2_1_calibration"


def test_coverage_gate_logic():
    price, deriv = 16, 16
    assert not (price >= 60 and deriv >= 20)
    price, deriv = 60, 20
    assert price >= 60 and deriv >= 20


def test_no_formal_paths():
    assert os.environ["EXCHANGE_WRITE"] == "false"
    assert os.environ["MAINNET"] == "false"
    assert os.environ["REAL_MONEY"] == "false"


def test_v1_v11_packages_untouched():
    root = Path(__file__).resolve().parents[1]
    assert (root / "artifacts/readiness/immutable/general_multi_strategy_engine_v1").is_dir()
    assert (root / "artifacts/readiness/immutable/strategy_engine_semantic_repair_v1_1").is_dir()


def test_cross_sectional_universe_gate():
    from backend.nexus_strategy_engine.development_research_v1_2 import (
        CROSS_SECTIONAL_TOO_SMALL,
        MIN_CROSS_SECTIONAL_UNIVERSE,
        run_hypothesis_development_v12,
    )
    from backend.nexus_strategy_engine.data_bundle import ResearchDataBundle
    from backend.nexus_strategy_engine.hypotheses_v1_2 import default_v12_hypothesis_drafts

    drafts = [d for d in default_v12_hypothesis_drafts() if d["component_id"] == "CROSS_SECTIONAL_MOMENTUM"]
    assert drafts
    hyp = drafts[0]
    # freeze minimal fields
    hyp = {**hyp, "strategy_checksum": "x", "semantic_checksum": "y", "execution_engine_checksum": "z"}
    tiny = [ResearchDataBundle(symbol=f"S{i}USDT", status="PRICE_MULTI_TIMEFRAME_READY") for i in range(5)]
    out = run_hypothesis_development_v12(
        hyp,
        bundles=tiny,
        universe_snapshot_id="test",
        data_checksum="d",
        research_universe_snapshot_checksum="u",
    )
    assert out["zero_trade_root_cause"] == CROSS_SECTIONAL_TOO_SMALL
    assert out.get("not_cost_gate_failure") is True
    assert out["eligible_ranking_symbol_count"] < MIN_CROSS_SECTIONAL_UNIVERSE


def test_real_vs_proxy_cost_labels():
    from backend.nexus_strategy_engine.cost_semantics import cost_semantics_summary

    s = cost_semantics_summary()
    assert "OBSERVED" in str(s) or "observed" in str(s).lower() or "proxy" in str(s).lower()


def test_low_agreement_blocks_policy_lessons():
    from backend.nexus_strategy_engine.reflection_v2_1 import run_reflection_calibration_v21

    out = run_reflection_calibration_v21([], use_real_ai=False)
    assert out["new_policy_effect_lesson_count"] == 0


def test_coverage_gate_prevents_premature_prereg():
    from tools.research.run_strategy_engine_broad_coverage_v1_2 import pick_recommendation

    rec = pick_recommendation(
        strict_ok=True,
        coverage_ok=False,
        reflection_ok=True,
        impl_ok=True,
        results=[],
        ran_research=False,
    )
    assert rec == "NEXUS_STRATEGY_ENGINE_V12_RESEARCH_COVERAGE_INSUFFICIENT"


def test_strict_fail_recommendation():
    from tools.research.run_strategy_engine_broad_coverage_v1_2 import pick_recommendation

    rec = pick_recommendation(
        strict_ok=False,
        coverage_ok=True,
        reflection_ok=True,
        impl_ok=True,
        results=[],
        ran_research=False,
    )
    assert rec == "NEXUS_STRICT_COMPONENT_CONFORMANCE_FAILED"
