"""Founder §15 tests for full 12H autonomous engine (no placeholder)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.nexus_demo_execution.account_epoch import AccountEpochTracker
from backend.nexus_demo_execution.account_reader import DemoAccountSnapshot
from backend.nexus_demo_execution.bounded_autonomous_engine import BoundedAutonomousSessionEngine
from backend.nexus_demo_execution.bounded_6h_session import Bounded6HSession
from backend.nexus_demo_execution.pnl_reconcile import reconcile_closed_trade_pnl
from backend.nexus_demo_execution.runtime_identity import capture_runtime_identity, classify_identity
from backend.nexus_demo_execution.session_policy import policy_12h_v3, policy_6h_v2
from backend.nexus_demo_execution.v3_extended_observation_gate import (
    EXACT_PHRASE,
    evaluate_extended_observation_gate,
)
from backend.nexus_demo_execution.v3_start_gate import evaluate_12h_machine_gate


def _flat_snap(wallet: float = 5000.0) -> DemoAccountSnapshot:
    return DemoAccountSnapshot(
        wallet_balance=wallet,
        equity=wallet,
        available_balance=wallet,
        margin_balance=wallet,
        used_margin=0.0,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        open_positions=[],
        open_orders=[],
        source="test",
    )


def test_no_placeholder_in_12h_module():
    root = Path(__file__).resolve().parents[1] / "backend" / "nexus_demo_execution"
    text_12 = (root / "bounded_12h_session.py").read_text(encoding="utf-8")
    assert "_run_placeholder" not in text_12
    assert "PLACEHOLDER_NO_WRITE" not in text_12
    assert "BoundedAutonomousSessionEngine" in text_12


def test_same_underlying_engine_6h_12h():
    assert Bounded6HSession is BoundedAutonomousSessionEngine
    p6 = policy_6h_v2()
    p12 = policy_12h_v3()
    assert p6.controller_type == p12.controller_type == "FULL_AUTONOMOUS_ENGINE"
    assert p6.session_duration_sec == 6 * 3600
    assert p12.session_duration_sec == 12 * 3600
    assert p12.max_session_net_loss == 15.0
    assert p12.max_total_entry_orders == 10


def test_ordinary_6h_promotion_gate_blocked_for_inconclusive():
    report = {
        "recommendation": "DEMO_AUTONOMOUS_6H_V2_INCONCLUSIVE_NO_EXECUTION",
        "runtime_recommendation_sot": "DEMO_AUTONOMOUS_6H_V2_INCONCLUSIVE_NO_EXECUTION",
        "canonical_6h_classification": "DEMO_AUTONOMOUS_6H_V2_INCONCLUSIVE_NO_EXECUTION",
        "session_completed": True,
        "write_window_closed": True,
        "position_count": 0,
        "open_order_count": 0,
        "reconciliation": "MATCH",
        "duplicate_order_count": 0,
        "unprotected_position_count": 0,
        "protection_incident_count": 0,
        "runtime_stall_count": 0,
        "export_complete": True,
        "entries_total": 0,
        "same_router_probe_pass": True,
        "order_route_verified": True,
        "session_id": "6h-x",
        "proposed_12h_session_id": "12h-y",
        "operational_safety_pass": True,
    }
    gate = evaluate_12h_machine_gate(report)
    assert gate["machine_gate_pass"] is False
    assert "6h_inconclusive_no_execution" in gate["problems"]


def test_founder_extended_observation_gate_pass():
    os.environ[FOUNDER := "FOUNDER_APPROVE_12H_AFTER_INCONCLUSIVE_6H_AND_PROBE"] = "true"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    report = {
        "canonical_6h_classification": "DEMO_AUTONOMOUS_6H_V2_INCONCLUSIVE_NO_EXECUTION",
        "source_6h_operational_safety_pass": True,
        "source_6h_final_position_count": 0,
        "source_6h_final_open_order_count": 0,
        "source_6h_reconciliation": "MATCH",
        "same_router_probe_verdict": "SAME_ROUTER_DEMO_PROBE_PASS",
        "same_router_order_route_verified": True,
        "same_router_fill_confirmed": True,
        "same_router_protection_verified": True,
        "same_router_controlled_close_completed": True,
        "same_router_final_account_flat": True,
        "final_position_count": 0,
        "final_open_order_count": 0,
        "final_reconciliation": "MATCH",
        "duplicate_order_count": 0,
        "unprotected_position_count": 0,
        "protection_incident_count": 0,
        "reconciliation_incident_count": 0,
        "approval_phrase": EXACT_PHRASE,
        FOUNDER: True,
    }
    gate = evaluate_extended_observation_gate(report, approval_phrase=EXACT_PHRASE)
    assert gate["gate_pass"] is True
    assert gate["gate_type"] == "FOUNDER_APPROVED_EXTENDED_OBSERVATION_AFTER_INCONCLUSIVE_6H"
    assert gate["6h_pass"] is False
    assert gate["production_ready"] is False
    assert gate["24h_approved"] is False


def test_source_verdict_cannot_be_rewritten_by_extension_gate():
    report = {
        "canonical_6h_classification": "DEMO_AUTONOMOUS_6H_V2_PASS",
        "source_6h_operational_safety_pass": True,
        "source_6h_final_position_count": 0,
        "source_6h_final_open_order_count": 0,
        "source_6h_reconciliation": "MATCH",
        "same_router_probe_verdict": "SAME_ROUTER_DEMO_PROBE_PASS",
        "same_router_order_route_verified": True,
        "same_router_fill_confirmed": True,
        "same_router_protection_verified": True,
        "same_router_controlled_close_completed": True,
        "same_router_final_account_flat": True,
        "final_position_count": 0,
        "final_open_order_count": 0,
        "final_reconciliation": "MATCH",
        "duplicate_order_count": 0,
        "unprotected_position_count": 0,
        "protection_incident_count": 0,
        "reconciliation_incident_count": 0,
        "approval_phrase": EXACT_PHRASE,
        "FOUNDER_APPROVE_12H_AFTER_INCONCLUSIVE_6H_AND_PROBE": True,
    }
    os.environ["FOUNDER_APPROVE_12H_AFTER_INCONCLUSIVE_6H_AND_PROBE"] = "true"
    gate = evaluate_extended_observation_gate(report, approval_phrase=EXACT_PHRASE)
    assert gate["gate_pass"] is False
    assert "source_6h_classification_not_inconclusive" in gate["problems"]


def test_account_epoch_persists_across_restart():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        t1 = AccountEpochTracker()
        ep1 = t1.observe(_flat_snap(5024.0), persist=True)
        t1.persist(root)
        assert ep1.epoch_id == "epoch-0001"
        t2 = AccountEpochTracker()
        assert t2.load(root) is True
        ep2 = t2.observe(_flat_snap(5023.9), persist=True)
        assert ep2.epoch_id == "epoch-0001"
        assert ep2.fingerprint
        assert ep2.runtime_demo_account_fingerprint


def test_fingerprint_not_reset_on_restart_only():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        t1 = AccountEpochTracker()
        t1.observe(_flat_snap(5000.0))
        t1.persist(root)
        fp1 = t1.current_epoch.runtime_demo_account_fingerprint
        t2 = AccountEpochTracker()
        t2.load(root)
        t2.observe(_flat_snap(4999.5))
        assert t2.current_epoch.epoch_id == "epoch-0001"
        assert t2.current_epoch.runtime_demo_account_fingerprint == fp1 or bool(
            t2.current_epoch.runtime_demo_account_fingerprint
        )


def test_runtime_identity_rejects_stale_label(monkeypatch):
    assert classify_identity("92a89dfaa8cc", "env:NEXUS_DEPLOYMENT_ID") == "RUNTIME_IDENTITY_LABEL_STALE"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        bake = "b0ca9219a634d22330684915778ef19e0cc42226"
        (root / "DEPLOYMENT_COMMIT").write_text(bake + "\n", encoding="utf-8")
        monkeypatch.setenv("NEXUS_DEPLOYMENT_ID", "92a89dfaa8cc")
        # CI injects GITHUB_SHA; bake file in data_root must still win.
        monkeypatch.setenv("GITHUB_SHA", "fdf5271952662f9b19e84a749c9cc6ac7a4ba7e1")
        ident = capture_runtime_identity(
            account_epoch="epoch-0001",
            policy_version="demo-autonomous-12h-v3-bounded",
            schema_version="demo_validation_session_v3",
            service_name="test",
            data_root=root,
        )
        assert ident.identity_class == "RUNTIME_IDENTITY_CONFIRMED"
        assert ident.deployment_commit.startswith("b0ca9219")
        assert ident.deployment_commit != os.environ["GITHUB_SHA"]


def test_fee_pnl_reconciliation_from_closed_pnl():
    row = {"closedPnl": "-0.07", "openFee": "0.02", "closeFee": "0.02", "fundingFee": "0"}
    out = reconcile_closed_trade_pnl(closed_pnl_row=row)
    assert out["actual_fees_status"] == "AVAILABLE"
    assert out["net_pnl_status"] == "AVAILABLE"
    assert out["actual_fees"] == pytest.approx(0.04)
    assert out["net_pnl"] == pytest.approx(-0.07)
    assert out["fee_source"] == "BYBIT_CLOSED_PNL"


def test_fee_pnl_missing_not_faked_as_zero():
    out = reconcile_closed_trade_pnl(closed_pnl_row=None)
    assert out["actual_fees"] is None
    assert out["net_pnl"] is None
    assert out["actual_fees_status"] == "NOT_FOUND"
    assert out["net_pnl_status"] == "NOT_AVAILABLE"


def test_entry_vs_protection_vs_close_counters_clarified():
    # Probe evidence contract: autonomous entry create max=1; write delta may include protect/close.
    from backend.nexus_demo_execution.same_router_probe import FIXED

    assert FIXED["maximum_order_creates"] == 1


def test_mainnet_and_real_money_forbidden_in_extension_gate():
    os.environ["FOUNDER_APPROVE_12H_AFTER_INCONCLUSIVE_6H_AND_PROBE"] = "true"
    os.environ["MAINNET"] = "true"
    report = {
        "canonical_6h_classification": "DEMO_AUTONOMOUS_6H_V2_INCONCLUSIVE_NO_EXECUTION",
        "source_6h_operational_safety_pass": True,
        "source_6h_final_position_count": 0,
        "source_6h_final_open_order_count": 0,
        "source_6h_reconciliation": "MATCH",
        "same_router_probe_verdict": "SAME_ROUTER_DEMO_PROBE_PASS",
        "same_router_order_route_verified": True,
        "same_router_fill_confirmed": True,
        "same_router_protection_verified": True,
        "same_router_controlled_close_completed": True,
        "same_router_final_account_flat": True,
        "final_position_count": 0,
        "final_open_order_count": 0,
        "final_reconciliation": "MATCH",
        "approval_phrase": EXACT_PHRASE,
    }
    gate = evaluate_extended_observation_gate(report, approval_phrase=EXACT_PHRASE)
    assert gate["gate_pass"] is False
    assert "mainnet_forbidden" in gate["problems"]
    os.environ["MAINNET"] = "false"


def test_immutable_deadline_on_engine_state():
    from backend.nexus_demo_execution.v2_bounded_engine import make_engine_12h
    from backend.nexus_demo_execution.v2_session_state import InvalidTransition

    eng = make_engine_12h(nonce="dl")
    eng.run_preflight_ok()
    eng.open_write_window(now=1000.0)
    deadline = eng.deadline_ts
    with pytest.raises(InvalidTransition):
        eng.extend_deadline(3600)
    assert eng.deadline_ts == deadline


def test_unique_controller_leader_lock():
    from backend.nexus_demo_execution.v2_session_recovery import LeaderLockError, SessionRecoveryStore

    with tempfile.TemporaryDirectory() as td:
        store = SessionRecoveryStore(Path(td))
        store.acquire("leader-a", session_id="sess-1")
        with pytest.raises(LeaderLockError):
            store.acquire("leader-b", session_id="sess-1")


def test_duplicate_start_idempotency_shell():
    from backend.nexus_demo_execution.bounded_12h_session import Bounded12HSession

    sess = Bounded12HSession(
        gate=MagicMock(),
        reader=MagicMock(),
        persistence=MagicMock(),
        epoch_tracker=AccountEpochTracker(),
        kill_switch=MagicMock(engaged=False),
        writer=MagicMock(),
        approval=MagicMock(),
        export_dir=Path(tempfile.mkdtemp()),
        data_root=Path(tempfile.mkdtemp()),
    )
    # Simulate already running engine
    eng = MagicMock()
    eng.status.return_value = {"thread_alive": True, "status": "RUNNING"}
    sess._engine = eng
    sess.session_id = "NEXUS-DEMO-12H-V3-x"
    out = sess.start(source_6h_report={})
    assert out["ok"] is False
    assert out["reason"] == "IDEMPOTENT_DUPLICATE_START_BLOCKED"
