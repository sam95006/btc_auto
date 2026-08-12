"""Tests for 6H/12H session state, kill switch, recovery, and start gates."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.nexus_demo_execution.v2_bounded_engine import make_engine_12h, make_engine_6h
from backend.nexus_demo_execution.v2_kill_switch import evaluate_kill_switch
from backend.nexus_demo_execution.v2_session_recovery import LeaderLockError, SessionRecoverySnapshot, SessionRecoveryStore
from backend.nexus_demo_execution.v2_session_state import COMPLETED, RUNNING, InvalidTransition, can_transition, transition
from backend.nexus_demo_execution.v3_policy import MAX_SESSION_NET_LOSS as V3_LOSS
from backend.nexus_demo_execution.v3_policy import MIN_NET_REWARD_RISK_RATIO as V3_RR
from backend.nexus_demo_execution.v3_start_gate import evaluate_12h_machine_gate
from backend.nexus_demo_execution.v2_policy import MAX_SESSION_NET_LOSS as V2_LOSS
from backend.nexus_demo_execution.v2_policy import MIN_NET_REWARD_RISK_RATIO as V2_RR


def test_net_rr_shared():
    assert V2_RR == 1.2
    assert V3_RR == 1.2
    assert V2_LOSS == 10.0
    assert V3_LOSS == 15.0


def test_no_running_extend_or_completed_reopen():
    assert can_transition(RUNNING, RUNNING) is False
    with pytest.raises(InvalidTransition):
        transition(COMPLETED, RUNNING)


def test_engine_deadline_and_no_extend():
    eng = make_engine_6h(nonce="abc")
    eng.run_preflight_ok()
    eng.open_write_window(now=1_000.0)
    assert eng.write_window_open is True
    assert eng.deadline_ts == 1_000.0 + 6 * 3600
    with pytest.raises(InvalidTransition):
        eng.extend_deadline(3600)
    assert eng.check_deadline(now=eng.deadline_ts) is True
    assert eng.write_window_open is False


def test_distinct_session_ids_6h_12h():
    a = make_engine_6h(nonce="n1")
    b = make_engine_12h(nonce="n1")
    assert a.session_id != b.session_id
    assert "6H-V2" in a.session_id
    assert "12H-V3" in b.session_id


def test_kill_switch_and_finalize():
    eng = make_engine_6h(nonce="kill")
    eng.run_preflight_ok()
    eng.open_write_window(now=1.0)
    eng.session_net_pnl = -11.0
    d = eng.evaluate_risk_and_maybe_kill()
    assert d["triggered"] is True
    assert eng.state == "KILLED"
    assert eng.write_window_open is False
    assert d["auto_restart"] is False


def test_kill_mainnet():
    d = evaluate_kill_switch(
        session_net_pnl=0,
        max_session_net_loss=10,
        last_trade_net_pnl=None,
        max_single_trade_net_loss=3,
        consecutive_losses=0,
        max_consecutive_losses=3,
        bad_process_outcomes=0,
        max_bad_process_outcomes=1,
        duplicate_orders=0,
        unprotected_positions=0,
        protection_verify_timeout=False,
        reconciliation="MATCH",
        execution_owner_count=1,
        persistence_ok=True,
        runtime_stall=False,
        fee_expired=False,
        mainnet=True,
        real_money=False,
    )
    assert d.triggered and d.reason == "MAINNET_DETECTED"


def test_recovery_preserves_counters():
    with tempfile.TemporaryDirectory() as td:
        store = SessionRecoveryStore(Path(td))
        snap = SessionRecoverySnapshot(
            session_id="NEXUS-DEMO-6H-V2-x",
            policy_version="p",
            state=RUNNING,
            deadline_ts=9999,
            entries_total=3,
            completed_trades=2,
            consecutive_losses=1,
            bad_process_outcomes=0,
            session_net_pnl=-1.5,
            write_window_open=True,
            leader_token="tok-a",
        )
        store.save(snap)
        store.acquire("tok-a", session_id=snap.session_id)
        with pytest.raises(LeaderLockError):
            store.acquire("tok-b", session_id=snap.session_id)
        out = store.recover_or_block(leader_token="tok-a", expected_session_id=snap.session_id)
        assert out["ok"] is True
        assert out["preserved"]["entries_total"] == 3
        assert out["preserved"]["deadline_ts"] == 9999


def test_12h_gate_blocks_failed_6h():
    bad = evaluate_12h_machine_gate({"recommendation": "DEMO_AUTONOMOUS_6H_V2_FAILED", "entries_total": 0})
    assert bad["machine_gate_pass"] is False
    assert bad["autonomous_execution_observed"] is False
    assert bad["12H_ALLOWED"] is False

    # Zero-entry PASS-like report must still block without execution / probe.
    zero = evaluate_12h_machine_gate(
        {
            "recommendation": "DEMO_AUTONOMOUS_6H_V2_PASS_WITH_FINDINGS",
            "runtime_recommendation_sot": "DEMO_AUTONOMOUS_6H_V2_FAILED",
            "orchestrator_recommendation": "DEMO_AUTONOMOUS_6H_V2_PASS_WITH_FINDINGS",
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
            "session_id": "6h-1",
            "proposed_12h_session_id": "12h-1",
            "findings": [],
        }
    )
    assert zero["machine_gate_pass"] is False
    assert "autonomous_execution_not_observed" in zero["problems"] or "zero_entries_without_same_router_probe" in zero["problems"]

    good = evaluate_12h_machine_gate(
        {
            "recommendation": "DEMO_AUTONOMOUS_6H_V2_PASS",
            "runtime_recommendation_sot": "DEMO_AUTONOMOUS_6H_V2_PASS",
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
            "entries_total": 1,
            "completed_trades_total": 1,
            "order_route_verified": True,
            "same_router_probe_pass": True,
            "session_id": "6h-1",
            "proposed_12h_session_id": "12h-1",
            "findings": [],
        }
    )
    assert good["machine_gate_pass"] is True
    assert good["auto_start_24h"] is False
    assert good["autonomous_execution_observed"] is True


def test_12h_gate_blocks_security_findings():
    r = evaluate_12h_machine_gate(
        {
            "recommendation": "DEMO_AUTONOMOUS_6H_V2_PASS_WITH_FINDINGS",
            "runtime_recommendation_sot": "DEMO_AUTONOMOUS_6H_V2_PASS_WITH_FINDINGS",
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
            "entries_total": 1,
            "order_route_verified": True,
            "same_router_probe_pass": True,
            "session_id": "6h-1",
            "proposed_12h_session_id": "12h-1",
            "findings": ["RUNTIME_STALL"],
        }
    )
    assert r["machine_gate_pass"] is False


def test_same_router_probe_dry_run():
    from backend.nexus_demo_execution.same_router_probe import SameRouterExecutionProbe

    out = SameRouterExecutionProbe().run(dry_run=True)
    assert out.ok is True
    assert out.reason == "DRY_RUN_PATH_IDENTITY_OK"
    d = out.to_dict()
    assert d["strategy_evidence"] is False
    assert d["same_order_router"] is True
    assert d["same_write_client"] is True
    assert d["exchange_write_attempt_total_delta"] == 0
    assert d["live_execution_proof"] is False


def test_12h_idempotent_duplicate_start():
    import tempfile
    from pathlib import Path
    from unittest.mock import MagicMock

    from backend.nexus_demo_execution.account_epoch import AccountEpochTracker
    from backend.nexus_demo_execution.bounded_12h_session import Bounded12HSession

    with tempfile.TemporaryDirectory() as td:
        s = Bounded12HSession(
            gate=MagicMock(),
            reader=MagicMock(),
            persistence=MagicMock(),
            epoch_tracker=AccountEpochTracker(),
            kill_switch=MagicMock(engaged=False),
            writer=MagicMock(),
            approval=MagicMock(),
            export_dir=Path(td),
            data_root=Path(td),
        )
        eng = MagicMock()
        eng.status.return_value = {"thread_alive": True, "status": "RUNNING"}
        s._engine = eng
        s.session_id = "NEXUS-DEMO-12H-V3-x"
        b = s.start(source_6h_report={"session_id": "6h-x"}, nonce="bbbb")
        assert b.get("ok") is False
        assert b.get("reason") == "IDEMPOTENT_DUPLICATE_START_BLOCKED"
