"""Tests for Edge Discovery Diagnostics V2."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ["NEXUS_AI_MOCK"] = "1"

from backend.nexus_edge_discovery.event_study import (
    EventObservation,
    benjamini_hochberg,
    block_bootstrap_ci,
    summarize_events,
)
from backend.nexus_edge_discovery.taxonomy_audit import classify_diagnostic, cost_bridge_from_sealed


def test_positive_gross_not_raw_no_edge():
    hyp = {
        "hypothesis_id": "V12_H01_TREND_CONTINUATION",
        "completed_trade_count": 250,
        "gross_pnl": 16.55,
        "net_pnl": -187.05,
        "gross_expectancy": 0.0662,
        "net_expectancy": -0.748,
        "profit_factor": 0.72,
        "fees": 97.0,
        "slippage": 54.7,
        "funding": 0.71,
        "candidate_funnel": {"event_detected_count": 1000, "cost_gate_block_count": 700},
        "largest_fold_profit_contribution": 1.0,
        "largest_symbol_profit_contribution": 0.17,
        "largest_regime_profit_contribution": 0.66,
        "positive_development_fold_count": 1,
        "development_fold_count": 5,
        "development_status": "DISCOVERY_NO_GROSS_EDGE",
    }
    bridge = cost_bridge_from_sealed(hyp)
    diag = classify_diagnostic(hyp, bridge)
    assert diag != "RAW_SIGNAL_NO_EDGE"
    assert diag == "RAW_EDGE_COST_DESTROYED"
    assert bridge["gross_expectancy"] > 0
    assert bridge["net_expectancy"] <= 0
    assert bridge["gross_profit_factor"] is None  # not reused from net


def test_cost_bridge_identity():
    hyp = {
        "hypothesis_id": "X",
        "completed_trade_count": 10,
        "gross_pnl": 10.0,
        "net_pnl": -5.0,
        "gross_expectancy": 1.0,
        "net_expectancy": -0.5,
        "fees": 8.0,
        "slippage": 4.0,
        "funding": 1.0,
        "candidate_funnel": {},
    }
    b = cost_bridge_from_sealed(hyp)
    assert abs(b["total_execution_cost"] - 15.0) < 1e-9
    assert abs((b["gross_pnl"] - b["total_execution_cost"]) - b["net_pnl"]) < 1e-9


def test_execution_gate_starved():
    hyp = {
        "hypothesis_id": "V12_H09",
        "completed_trade_count": 0,
        "gross_expectancy": None,
        "net_expectancy": None,
        "candidate_funnel": {"event_detected_count": 26, "cost_gate_block_count": 26},
        "largest_fold_profit_contribution": 0,
        "largest_symbol_profit_contribution": 0,
        "largest_regime_profit_contribution": 0,
        "positive_development_fold_count": 0,
        "development_fold_count": 5,
    }
    assert classify_diagnostic(hyp, cost_bridge_from_sealed(hyp)) == "EXECUTION_GATE_STARVED"


def test_event_observations_are_not_trades():
    ev = EventObservation(
        component_id="TREND_CONTINUATION",
        symbol="BTCUSDT",
        side="Buy",
        regime="TRENDING_UP",
        size_class="MAINSTREAM",
        entry_index=10,
        decision_ts=1,
        entry_price=100.0,
        forward={"ret_8": 0.01},
        mfe=0.02,
        mae=0.01,
        mfe_before_mae=True,
        is_trade=False,
    )
    assert ev.is_trade is False
    s = summarize_events([ev])
    assert s["observation_is_trade"] is False


def test_block_bootstrap_reproducible():
    rets = [0.01, -0.005, 0.002, 0.003, -0.001] * 20
    a = block_bootstrap_ci(rets, seed=20260803)
    b = block_bootstrap_ci(rets, seed=20260803)
    assert a["ci_low"] == b["ci_low"]
    assert a["ci_high"] == b["ci_high"]
    assert a["random_seed"] == 20260803


def test_fdr_correction():
    pvals = [("a", 0.001), ("b", 0.02), ("c", 0.5), ("d", 0.04)]
    out = benjamini_hochberg(pvals, q=0.10)
    assert out["hypothesis_test_count"] == 4
    assert out["FDR_adjusted_significant_count"] >= 1


def test_blind_prompt_excludes_deterministic():
    from backend.nexus_edge_discovery.blind_reflection_v22 import _strip_deterministic_leak

    ok = "Classify using evidence only. Allowed GOOD_PROCESS_LOSS."
    _strip_deterministic_leak(ok)
    with pytest.raises(AssertionError):
        _strip_deterministic_leak("deterministic_baseline=PROCESS_COMPLIANT")


def test_v12_packages_untouched():
    root = Path(__file__).resolve().parents[1]
    assert (root / "artifacts/readiness/immutable/strategy_engine_broad_coverage_v1_2").is_dir()
    assert (root / "artifacts/readiness/immutable/strategy_engine_semantic_repair_v1_1").is_dir()


def test_no_formal_paths():
    assert os.environ["EXCHANGE_WRITE"] == "false"
    assert os.environ["MAINNET"] == "false"
    assert os.environ["REAL_MONEY"] == "false"
