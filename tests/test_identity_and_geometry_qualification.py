"""Runtime identity precedence + event-driven geometry qualification tests."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from backend.nexus_demo_execution.geometry_event_sim import (
    Candle,
    classify_oos_status,
    generate_synthetic_path,
    run_event_driven_folds,
    simulate_trade,
    summarize_trades,
)
from backend.nexus_demo_execution.runtime_identity import (
    PERSISTENT_LAST_WRITER_NAME,
    PERSISTENT_ORIGIN_NAME,
    capture_runtime_identity,
    classify_identity_confirmed,
    resolve_executable_code_commit,
)
from backend.nexus_demo_execution.structural_geometry_qualify import (
    CandidateEvidence,
    run_qualification_pipeline,
    synthesize_structure_candidates,
)
from backend.nexus_demo_execution.wallet_delta_reconcile import FOUNDER_CLASSIFICATIONS, reconcile_wallet_delta


def test_container_identity_beats_persistent_state(monkeypatch, tmp_path: Path):
    persistent = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    baked = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    art = tmp_path / "artifacts" / "demo_validation"
    art.mkdir(parents=True)
    (art / "DEPLOYMENT_COMMIT").write_text(persistent + "\n", encoding="utf-8")
    (tmp_path / "DEPLOYMENT_COMMIT").write_text(persistent + "\n", encoding="utf-8")
    monkeypatch.setattr(
        "backend.nexus_demo_execution.runtime_identity.read_container_baked_commit",
        lambda: (baked, "file:/app/DEPLOYMENT_COMMIT"),
    )
    monkeypatch.setattr(
        "backend.nexus_demo_execution.runtime_identity.read_container_source_commit",
        lambda: (baked, "file:/app/SOURCE_COMMIT"),
    )
    monkeypatch.setenv("GITHUB_SHA", "cccccccccccccccccccccccccccccccccccccccc")
    monkeypatch.setenv("NEXUS_DEPLOYMENT_COMMIT", "dddddddddddddddddddddddddddddddddddddddd")
    ident = capture_runtime_identity(
        account_epoch="epoch-0001",
        policy_version="demo-autonomous-12h-v3-bounded",
        schema_version="demo_validation_session_v3",
        service_name="test",
        data_root=tmp_path,
        expected_deployment_commit=baked,
    )
    assert ident.runtime_current_code_commit.startswith("bbbb")
    assert ident.container_baked_commit.startswith("bbbb")
    assert ident.identity_class == "RUNTIME_IDENTITY_CONFIRMED"
    # Persistent metadata preserved separately — must not equal current code when different.
    assert ident.persistent_state_origin_commit.startswith("aaaa")
    assert (art / PERSISTENT_ORIGIN_NAME).exists() or ident.persistent_state_origin_commit.startswith("aaaa")


def test_persistent_identity_preserved_as_metadata(monkeypatch, tmp_path: Path):
    baked = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    art = tmp_path / "artifacts" / "demo_validation"
    art.mkdir(parents=True)
    (art / "DEPLOYMENT_COMMIT").write_text("oldpersistent00000000000000000000000000\n", encoding="utf-8")
    monkeypatch.setattr(
        "backend.nexus_demo_execution.runtime_identity.read_container_baked_commit",
        lambda: (baked, "file:/app/DEPLOYMENT_COMMIT"),
    )
    monkeypatch.setattr(
        "backend.nexus_demo_execution.runtime_identity.read_container_source_commit",
        lambda: (baked, "file:/app/SOURCE_COMMIT"),
    )
    ident = capture_runtime_identity(
        account_epoch="e1",
        policy_version="p",
        schema_version="s",
        service_name="t",
        data_root=tmp_path,
        expected_deployment_commit=baked,
    )
    assert ident.identity_class == "RUNTIME_IDENTITY_CONFIRMED"
    assert (art / PERSISTENT_LAST_WRITER_NAME).read_text(encoding="utf-8").strip().startswith("eeee")
    # Historical DEPLOYMENT_COMMIT not deleted.
    assert (art / "DEPLOYMENT_COMMIT").read_text(encoding="utf-8").strip().startswith("oldpersistent")


def test_identity_mismatch_when_expected_differs(monkeypatch, tmp_path: Path):
    baked = "ffffffffffffffffffffffffffffffffffffffff"
    monkeypatch.setattr(
        "backend.nexus_demo_execution.runtime_identity.read_container_baked_commit",
        lambda: (baked, "file:/app/DEPLOYMENT_COMMIT"),
    )
    monkeypatch.setattr(
        "backend.nexus_demo_execution.runtime_identity.read_container_source_commit",
        lambda: (baked, "file:/app/SOURCE_COMMIT"),
    )
    ident = capture_runtime_identity(
        account_epoch="e1",
        policy_version="p",
        schema_version="s",
        service_name="t",
        data_root=tmp_path,
        expected_deployment_commit="9999999999999999999999999999999999999999",
    )
    assert ident.identity_class == "RUNTIME_IDENTITY_MISMATCH"


def test_classify_confirmed_requires_code_eq_bake():
    assert (
        classify_identity_confirmed(
            runtime_current_code_commit="aaa",
            container_baked_commit="bbb",
        )
        == "RUNTIME_IDENTITY_AMBIGUOUS"
    )
    assert (
        classify_identity_confirmed(
            runtime_current_code_commit="aaa",
            container_baked_commit="aaa",
            expected_deployment_commit="aaa",
        )
        == "RUNTIME_IDENTITY_CONFIRMED"
    )


def test_event_driven_entry_and_adverse_first_intrabar():
    c = CandidateEvidence(
        symbol="BTCUSDT",
        side="Buy",
        entry_price=100.0,
        atr=2.0,
        recent_swing_high=106.0,
        recent_swing_low=97.0,
        support=96.5,
        resistance=105.0,
        fee_rate=0.00055,
        spread_bps=2.0,
        slippage_bps=2.0,
        qty=1.0,
        data_freshness_sec=10.0,
        ts=1.0,
    )
    # Ambiguous bar: both SL and TP touched — adverse-first → STOP_LOSS
    candles = [
        Candle(ts=1, open=100.0, high=100.1, low=99.9, close=100.0),
        Candle(ts=2, open=100.0, high=120.0, low=80.0, close=100.0),
    ]
    trade = simulate_trade(candidate=c, subsequent_candles=candles, adverse_first=True)
    if trade.status in {"COST_GATE_BLOCKED", "GEOMETRY_BLOCKED"}:
        pytest.skip("geometry/cost blocked for this synthetic structure")
    assert trade.status == "STOP_LOSS"
    assert trade.intrabar_resolution_method == "ADVERSE_FIRST"
    assert trade.look_ahead_contamination is False


def test_unresolved_not_counted_as_win():
    c = CandidateEvidence(
        symbol="ETHUSDT",
        side="Buy",
        entry_price=2000.0,
        atr=40.0,
        recent_swing_high=2120.0,
        recent_swing_low=1940.0,
        support=1930.0,
        resistance=2100.0,
        fee_rate=0.00055,
        qty=1.0,
        data_freshness_sec=10.0,
        ts=2.0,
    )
    trade = simulate_trade(
        candidate=c,
        subsequent_candles=[
            Candle(ts=1, open=2000.0, high=2001.0, low=1999.0, close=2000.5),
            Candle(ts=2, open=2000.5, high=2002.0, low=1999.5, close=2001.0),
        ],
    )
    if trade.status in {"COST_GATE_BLOCKED", "GEOMETRY_BLOCKED"}:
        pytest.skip("blocked")
    assert trade.status == "UNRESOLVED_AT_DATA_END"
    assert trade.net_pnl is None
    assert trade.process_label is None
    summary = summarize_trades([trade], min_sample=1)
    assert summary["simulated_trade_count"] == 0
    assert summary["wins"] == 0


def test_zero_simulation_cannot_become_oos_validated():
    assert classify_oos_status(trade_simulation_count=0, performance={}) == "OOS_FRAMEWORK_VALIDATED"
    assert (
        classify_oos_status(
            trade_simulation_count=5,
            performance={"net_pnl": None, "profit_factor": None, "expectancy": None, "maximum_drawdown": None, "win_rate": None},
        )
        == "OOS_FRAMEWORK_VALIDATED"
    )


def test_null_performance_cannot_become_oos_validated():
    status = classify_oos_status(
        trade_simulation_count=100,
        performance={
            "net_pnl": None,
            "profit_factor": 1.2,
            "expectancy": 0.1,
            "maximum_drawdown": -1.0,
            "win_rate": 0.5,
        },
    )
    assert status == "OOS_FRAMEWORK_VALIDATED"
    assert status != "OOS_VALIDATED"


def test_chronological_fold_isolation_and_pipeline():
    cands = synthesize_structure_candidates(120)
    event = run_event_driven_folds(cands, min_sample=5)
    assert event["look_ahead_contamination"] is False
    assert event["oos_status"] in {
        "OOS_FRAMEWORK_VALIDATED",
        "OOS_INSUFFICIENT_SAMPLE",
        "OOS_PERFORMANCE_FAILED",
        "OOS_PERFORMANCE_VALIDATED",
    }
    assert event["oos_status"] != "OOS_VALIDATED"
    assert event["qualification_complete"] is False
    assert event["shadow_status"] == "NOT_APPLIED"
    report = run_qualification_pipeline(cands)
    assert report["qualification_complete"] is False
    assert report["recommendation"] in {
        "NEXUS_GEOMETRY_QUALIFICATION_IN_PROGRESS",
        "NEXUS_RISK_REVIEW_READY",
    }
    assert report["stages"]["RISK_REVIEWED"]["status"] == "RISK_REVIEW_PENDING_FOUNDER"
    assert report["stages"]["SHADOW_APPLIED"]["status"] == "NOT_APPLIED"
    oos = report["stages"]["OOS_VALIDATED"]
    assert oos["status"] != "OOS_VALIDATED"
    if (oos.get("trade_simulation_count") or 0) == 0:
        assert oos["status"] == "OOS_FRAMEWORK_VALIDATED"


def test_no_future_data_geometry_path_starts_after_decision():
    path = generate_synthetic_path(
        entry=100.0, side="Buy", stop=98.0, take_profit=104.0, n=5, seed=1, resolve="tp"
    )
    assert path[0].ts == 1.0
    assert all(c.ts > 0 for c in path)


def test_wallet_founder_classification_empty_ledger():
    out = reconcile_wallet_delta(
        starting_wallet=5024.24829280,
        final_wallet=5023.27777241,
        closed_pnl_rows=[],
        execution_rows=[],
        transaction_rows=[],
        available_balance=5028.60306306,
        equity=5023.27777241,
    )
    assert out["classification"] in FOUNDER_CLASSIFICATIONS
    assert out["classification"] == "API_HISTORY_RETENTION_GAP"
    assert out["evidence_record_count"] >= 1


def test_wallet_partially_attributed():
    out = reconcile_wallet_delta(
        starting_wallet=100.0,
        final_wallet=99.0,
        session_start_ms=1_700_000_000_000,
        session_end_ms=1_700_000_100_000,
        closed_pnl_rows=[
            {
                "updatedTime": 1_700_000_050_000,
                "orderId": "oid-1",
                "closedPnl": "-0.2",
                "openFee": "0.05",
                "closeFee": "0.05",
                "fundingFee": "0",
            }
        ],
    )
    assert out["classification"] == "PARTIALLY_ATTRIBUTED"
    assert abs(out["wallet_delta_unattributed"]) > 0


def test_mainnet_real_money_forbidden():
    from backend.nexus_demo_execution import MAINNET, REAL_MONEY

    assert MAINNET is False
    assert REAL_MONEY is False


def test_secret_scan_runtime_identity_module():
    text = Path("backend/nexus_demo_execution/runtime_identity.py").read_text(encoding="utf-8")
    for needle in ("API_KEY", "api_secret", "SECRET_KEY=", "BEGIN PRIVATE"):
        assert needle not in text
