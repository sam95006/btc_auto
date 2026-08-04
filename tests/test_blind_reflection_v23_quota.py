"""Tests for quota-aware V2.3 semantics, ratios, and VWAP independence."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ["NEXUS_AI_MOCK"] = "1"

from backend.nexus_edge_discovery.blind_reflection_v23 import (
    build_calibration_set_v23,
    migrate_process_classification,
)
from backend.nexus_edge_discovery.learning_prevention_proof import (
    run_good_process_loss_non_suppression_test,
    run_learning_prevention_proof,
)
from backend.nexus_edge_discovery.quota_aware_v23 import (
    build_initial_checkpoint,
    evaluate_quality,
    run_quota_aware_calibration,
)
from backend.nexus_edge_discovery.ratio_metrics import make_ratio


def _packets():
    rows = []
    for i in range(70):
        pnl = 1.0 if i % 2 == 0 else -0.9
        rows.append(
            {
                "symbol": ["BTCUSDT", "ETHUSDT", "SOLUSDT"][i % 3],
                "side": "Buy" if pnl > 0 else "Sell",
                "regime": ["TRENDING_UP", "RANGE", "TRENDING_DOWN"][i % 3],
                "entry_status": "ENTRY_FILLED",
                "entry_price": 100.0,
                "stop": 98.0 if pnl > 0 else 102.0,
                "take_profit": 104.0 if pnl > 0 else 96.0,
                "entry_ts": 1_750_000_000_000 + i * 900_000,
                "exit_price": 103.0 if pnl > 0 else 99.0,
                "exit_status": "TARGET" if pnl > 0 else "STOP",
                "gross_pnl": pnl,
                "net_pnl": pnl * 0.9,
                "fees": 0.05,
                "slippage": 0.02,
                "funding": 0.0,
                "holding_bars": 8,
                "mfe": abs(pnl) * 1.2,
                "mae": abs(pnl) * 0.4,
            }
        )
    hyps = [
        {
            "strategy_id": "V12_H01",
            "hypothesis_id": "V12_H01",
            "strategy_family": "TREND",
            "component_id": "TREND_CONTINUATION",
            "event_definition": "x",
            "stop_definition": "atr",
            "target_definition": "rr",
        }
    ]
    return build_calibration_set_v23(
        market_rows=rows,
        hypotheses=hyps,
        universe_snapshot_id="u",
        data_checksum="d",
    )


def test_zero_denominator_not_one():
    r = make_ratio(0, 0)
    assert r["status"] == "NOT_APPLICABLE"
    assert r["value"] is None
    assert r["denominator"] == 0


def test_429_not_counted_as_ai_insufficient():
    packets = _packets()
    state = build_initial_checkpoint(packets=packets, manifest_checksum="x", model_id="m")
    state["provider_429_count"] = 80
    q = evaluate_quality(state, {str(p["trade_id"]): p for p in packets})
    assert q["provider_successful_response_count"] == 0
    assert q["AI_evidence_sufficiency_assessed_count"] == 0
    assert q["AI_evidence_insufficient_count"] == 0
    assert q["undetermined_count"] == 0
    assert q["V2_3_quality_status"] == "INCOMPLETE_PROVIDER_CAPACITY"
    assert q["critic_resolution_status"] == "NOT_APPLICABLE"
    assert q["critic_resolution_denominator"] == 0
    assert q["critic_resolution_ratio"]["value"] is None


def test_undetermined_migration():
    assert migrate_process_classification("UNDETERMINED_PROCESS") == "UNDETERMINED"


def test_quota_aware_mock_completes_or_progresses(tmp_path: Path):
    # Use temp root with .nexus_runtime
    root = tmp_path
    packets = _packets()
    out = run_quota_aware_calibration(
        root=root,
        packets=packets,
        manifest_checksum="mock_manifest",
        use_real_ai=False,
        max_batches_this_invocation=20,
    )
    assert out["quality"]["provider_successful_response_count"] == 80
    assert out["quality"]["quality_gates_evaluated"] is True
    assert out["quality"]["evidence_packet_delivery_ratio"]["value"] == 1.0
    # resume skips completed
    out2 = run_quota_aware_calibration(
        root=root,
        packets=packets,
        manifest_checksum="mock_manifest",
        use_real_ai=False,
        max_batches_this_invocation=1,
    )
    assert out2["quality"]["provider_successful_response_count"] == 80
    assert out2["state_summary"]["calibration_pending_case_count"] == 0


def test_control_proof_not_real_learning():
    packets = _packets()
    control = run_learning_prevention_proof(
        packets=packets, use_real_ai=False, proof_level="CONTROL_CHAIN_PROOF"
    )
    assert control["label"] == "CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING"
    assert control["misrepresented_as_real_learning"] is False
    assert control["control_chain_proof_status"] == "PASS"
    real = run_learning_prevention_proof(
        packets=packets, use_real_ai=False, proof_level="REAL_HISTORICAL_CHAIN_PROOF"
    )
    # Synthetic pads may or may not yield noncompliant real sources; status must be honest
    assert real["real_historical_chain_proof_status"] in {
        "PASS",
        "FAIL",
        "NO_ELIGIBLE_BAD_PROCESS_SOURCE",
    }
    assert real.get("misrepresented_as_real_learning") is not True


def test_gpl_and_hard_bans():
    packets = _packets()
    gpl = run_good_process_loss_non_suppression_test(packets)
    assert gpl["good_process_loss_non_suppression_status"] == "PASS"
    assert os.environ["EXCHANGE_WRITE"] == "false"
    assert os.environ["MAINNET"] == "false"
    assert os.environ["REAL_MONEY"] == "false"


def test_vwap_independent_of_reflection_gate():
    from backend.nexus_edge_discovery.conditional_vwap_confirmation import (
        VWAP_INDEPENDENT_OF_REFLECTION_QUALITY,
        run_conditional_vwap_confirmation,
    )

    assert VWAP_INDEPENDENT_OF_REFLECTION_QUALITY is True
    root = Path(__file__).resolve().parents[1]
    # Empty bundles -> data invalid but executed path (not skipped for reflection)
    out = run_conditional_vwap_confirmation(
        root=root,
        bundles=[],
        universe_snapshot_id="u",
        data_checksum="d",
        research_universe_snapshot_checksum="u",
        gates_passed=False,
        require_reflection_quality=False,
    )
    assert out["conditional_vwap_confirmation_executed"] is True
    assert out["vwap_confirmation_status"] != "VWAP_DEVELOPMENT_SKIPPED_GATES_FAILED"
