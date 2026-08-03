"""V1.1 semantic execution repair tests."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ["NEXUS_AI_MOCK"] = "1"

ROOT = Path(__file__).resolve().parents[1]

from backend.nexus_demo_execution.historical_market_data import Candle
from backend.nexus_strategy_engine.components import COMPONENT_IDS
from backend.nexus_strategy_engine.conformance_fixtures import run_all_conformance
from backend.nexus_strategy_engine.cost_semantics import annotate_trade_costs
from backend.nexus_strategy_engine.data_bundle import (
    compute_partition_integrity,
    load_research_data_bundles,
    resample_ohlcv,
)
from backend.nexus_strategy_engine.development_research_v1_1 import (
    build_candidates_for_component,
    classify_discovery_v11,
)
from backend.nexus_strategy_engine.executors import (
    FundingOiContinuationExecutor,
    MarkIndexBasisExecutor,
    RelativeStrengthExecutor,
    get_executor,
    executor_registry,
)
from backend.nexus_strategy_engine.hypotheses_v1_1 import default_v11_hypothesis_drafts, preregister_v11_hypotheses
from backend.nexus_strategy_engine.lesson_seal import lesson_may_influence_development
from backend.nexus_strategy_engine.semantic_collision import (
    V1_EXECUTION_INTERPRETATION,
    audit_semantic_collisions,
)


def _candles(n=100, base=100.0):
    out = []
    t0 = 1_700_000_000_000
    for i in range(n):
        px = base * (1 + 0.001 * i)
        out.append(Candle(ts_ms=t0 + i * 900_000, open=px, high=px * 1.01, low=px * 0.99, close=px, volume=100))
    return out


def test_no_family_fallback_distinct_executors():
    reg = executor_registry()
    assert reg["family_bucket_dispatch_removed"] is True
    assert reg["implemented_component_count"] == 16
    classes = {c["executor_class"] for c in reg["components"]}
    assert len(classes) == 16
    # Unknown component is NOT_IMPLEMENTED — no silent fallback to another
    from backend.nexus_strategy_engine.executors import NotImplementedExecutor, ScanContext

    unknown = get_executor("NOT_A_REAL_COMPONENT")
    assert isinstance(unknown, NotImplementedExecutor)
    assert unknown.implemented is False
    assert unknown.scan(ScanContext(symbol="X", candles_15=_candles())) == []


def test_semantic_collision_audit_on_v1_package():
    path = ROOT / "artifacts/readiness/immutable/general_multi_strategy_engine_v1/development_research_summary.json"
    if not path.is_file():
        pytest.skip("V1 package missing")
    import json

    v1 = json.loads(path.read_text(encoding="utf-8"))
    audit = audit_semantic_collisions(v1)
    assert audit["V1_EXECUTION_INTERPRETATION"] == V1_EXECUTION_INTERPRETATION
    assert audit["distinct_strategy_pair_count"] >= 1
    assert audit["semantic_collision_pair_count"] >= 1


def test_cross_sectional_requires_peer_ranking():
    ex = RelativeStrengthExecutor()
    from backend.nexus_strategy_engine.executors import ScanContext

    # Without peers → no signals
    assert ex.scan(ScanContext(symbol="ETHUSDT", candles_15=_candles(80))) == []
    peers = {f"S{i}USDT": 0.01 * i for i in range(10)}
    peers["ETHUSDT"] = 0.09
    peers["BTCUSDT"] = 0.01
    sigs = ex.scan(
        ScanContext(
            symbol="ETHUSDT",
            candles_15=_candles(80),
            peer_returns_at_ts=peers,
            btc_return_at_ts=0.01,
        )
    )
    assert isinstance(sigs, list)


def test_funding_oi_requires_actual_series_no_proxy():
    ex = FundingOiContinuationExecutor()
    from backend.nexus_strategy_engine.executors import ScanContext

    c15 = _candles(80)
    # Missing funding/OI → empty, never price proxy
    assert ex.scan(ScanContext(symbol="BTCUSDT", candles_15=c15)) == []
    assert ex.scan(ScanContext(symbol="BTCUSDT", candles_15=c15, funding_points=[{"ts_ms": c15[0].ts_ms, "funding_rate": 0.0001}])) == []


def test_mark_index_requires_actual_series():
    ex = MarkIndexBasisExecutor()
    from backend.nexus_strategy_engine.executors import ScanContext

    c15 = _candles(80)
    assert ex.scan(ScanContext(symbol="BTCUSDT", candles_15=c15)) == []


def test_strategy_specific_exits_differ():
    stops = set()
    targets = set()
    for cid in ("TREND_CONTINUATION", "BREAKOUT", "VWAP_MEAN_REVERSION", "LIQUIDITY_SWEEP_REVERSAL"):
        ex = get_executor(cid)
        assert ex.implemented
        # checksums distinct
        stops.add(ex.checksum())
    assert len(stops) == 4


def test_multi_timeframe_asof_resample_no_future():
    c15 = _candles(96)
    c60 = resample_ohlcv(c15, target_interval="60")
    assert c60
    assert c60[-1].ts_ms <= c15[-1].ts_ms
    assert all(c60[i].ts_ms <= c60[i + 1].ts_ms for i in range(len(c60) - 1))


def test_complete_partition_checksum_and_gap_detection():
    c = _candles(20)
    integ = compute_partition_integrity(c, interval="15")
    assert integ["full_partition_checksum"]
    assert integ["record_count"] == 20
    assert integ["duplicate_interval_count"] == 0
    # inject gap
    gappy = c[:10] + c[12:]
    integ2 = compute_partition_integrity(gappy, interval="15")
    assert integ2["missing_interval_count"] >= 1
    # inject duplicate
    dup = c + [c[-1]]
    integ3 = compute_partition_integrity(sorted(dup, key=lambda x: x.ts_ms), interval="15")
    assert integ3["duplicate_interval_count"] >= 1


def test_proxy_costs_labeled():
    row = annotate_trade_costs({"net_pnl": 1}, spread_bps=6, slip_bps=6, has_orderbook=False)
    assert row["spread_source"] == "CONSERVATIVE_PROXY"
    assert row["slippage_source"] == "CONSERVATIVE_PROXY"
    assert row["observed_execution_data"] is False


def test_zero_trade_root_cause_reported():
    from backend.nexus_strategy_engine.data_bundle import ResearchDataBundle
    from backend.nexus_strategy_engine.hypotheses_v1_1 import default_v11_hypothesis_drafts
    from backend.nexus_strategy_engine.strategy_spec import freeze_spec

    hyp = freeze_spec([d for d in default_v11_hypothesis_drafts() if d["component_id"] == "FUNDING_OI_CONTINUATION"][0])
    bundles = [
        ResearchDataBundle(
            symbol="BTCUSDT",
            status="PRICE_MULTI_TIMEFRAME_READY",
            candles_15=_candles(100),
            candles_60=_candles(40),
            candles_240=_candles(20),
            funding_points=[],
            oi_points=[],
        )
    ]
    pairs, funnel, cause, proxy = build_candidates_for_component(hyp, bundles=bundles)
    assert pairs == []
    assert cause == "REQUIRED_DATA_MISSING"
    assert proxy == 0


def test_all_component_conformance_fixtures():
    summary = run_all_conformance()
    assert summary["component_conformance_test_count"] >= 80
    assert summary["component_conformance_failure_count"] == 0
    assert summary["label"] == "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE"


def test_integration_lessons_cannot_influence_policy():
    assert lesson_may_influence_development("INTEGRATION_PROOF_ONLY") is False


def test_low_quality_reflection_blocks_policy_lessons():
    from backend.nexus_strategy_engine.reflection_v2_1 import run_reflection_calibration_v21

    # Empty / insufficient packets → quality fail → policy lessons 0
    out = run_reflection_calibration_v21([], use_real_ai=False)
    # empty edge case — still no policy lessons
    assert out["new_policy_effect_lesson_count"] == 0


def test_hard_risk_constants_unchanged():
    from backend.nexus_strategy_engine.constants import LEVERAGE, MAX_LOSS_RISK_PER_TRADE, POSITION_MARGIN_USDT

    assert LEVERAGE == 25
    assert POSITION_MARGIN_USDT == 20.0
    assert MAX_LOSS_RISK_PER_TRADE == 3.0


def test_v11_preregistration_does_not_mutate_v1_ids():
    pre = preregister_v11_hypotheses()
    assert pre["v1_twelve_mutated"] is False
    assert all(h["strategy_id"].startswith("V11_") for h in pre["hypotheses"])
    assert pre["distinct_component_count"] >= 6
    assert pre["formal_walk_forward_forbidden_in_this_task"] is True
    assert pre["oos_creation_forbidden"] is True
    assert pre["demo_forbidden"] is True


def test_no_formal_wf_oos_demo_in_classifier():
    s = classify_discovery_v11(
        {
            "completed_trade_count": 60,
            "development_fold_count": 5,
            "positive_development_fold_count": 3,
            "net_expectancy": 0.5,
            "gross_expectancy": 0.6,
            "profit_factor": 1.2,
            "adverse_profit_factor": 1.05,
            "largest_fold_profit_contribution": 0.4,
            "largest_symbol_profit_contribution": 0.3,
            "largest_regime_profit_contribution": 0.4,
            "lookahead_violation_count": 0,
            "risk_limit_breach_count": 0,
            "semantic_execution_collision": False,
            "required_data_proxy_violation_count": 0,
        }
    )
    assert s == "DISCOVERY_PROMISING"


def test_bundles_load_without_hardcoded_integrity():
    bundles = load_research_data_bundles(ROOT)
    if not bundles:
        pytest.skip("no local datasets")
    for b in bundles[:3]:
        assert "missing_interval_count" in b.integrity_15
        assert b.integrity_15.get("full_partition_checksum")
