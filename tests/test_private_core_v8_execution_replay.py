"""V8 execution simulator, sessions, historical replay, ledger scale tests."""
from __future__ import annotations

import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"

from backend.nexus_autonomy.execution_simulator_v1 import AutonomousExecutionSimulatorV1
from backend.nexus_autonomy.historical_integration_replay_v1 import run_historical_integration_replay
from backend.nexus_autonomy.session_orchestrator_v1 import AutonomousSessionOrchestratorV1


def test_execution_duplicate_and_ambiguous(tmp_path: Path):
    sim = AutonomousExecutionSimulatorV1(max_positions=1, max_intents=1)
    a = sim.create_order(
        {"idempotency_key": "k", "symbol": "BTCUSDT", "side": "BUY", "order_type": "market", "qty": 0.1, "mark_price": 100}
    )
    assert a["status"] == "ACCEPTED", a
    b = sim.create_order(
        {"idempotency_key": "k", "symbol": "BTCUSDT", "side": "BUY", "order_type": "market", "qty": 0.1, "mark_price": 100}
    )
    assert b["status"] == "DUPLICATE_IGNORED"
    amb = AutonomousExecutionSimulatorV1()
    o = amb.create_order(
        {
            "idempotency_key": "a",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "order_type": "stop-market",
            "qty": 0.1,
            "mark_price": 100,
            "stop_price": 99.5,
        }
    )
    assert o["status"] == "ACCEPTED", o
    r = amb.try_fill(
        o["order_id"],
        market_bid=99.4,
        market_ask=100.1,
        last_price=100,
        path_low=99,
        path_high=101,
        same_bar_stop=99.5,
        same_bar_target=100.5,
    )
    assert r["status"] == "BLOCKED_AMBIGUOUS"


def test_session_a_invariants(tmp_path: Path):
    orch = AutonomousSessionOrchestratorV1(tmp_path, max_positions=1, max_intents=1)
    cands = [
        {"candidate_id": f"c{i}", "idempotency_key": f"c{i}", "symbol": "BTCUSDT", "side": "BUY", "mark_price": 100 + i}
        for i in range(10)
    ]
    rep = orch.run_accelerated_session(
        session_id="t6",
        logical_hours=6,
        candidates=cands,
        injections=["process_restart", "provider_outage", "stale_data", "duplicate_intent"],
        restart_at_index=2,
    )
    orch.close()
    assert rep["exchange_write_attempt_count"] == 0
    assert rep["unclosed_intent_count"] == 0
    assert rep["orphan_lifecycle_count"] == 0
    assert rep["session_pass"] is True


def test_historical_replay_min_500():
    root = Path(__file__).resolve().parents[1]
    r = run_historical_integration_replay(root, target_candidates=500)
    assert r["historical_candidate_count"] >= 500
    assert r["historical_replay_status"] == "NEXUS_HISTORICAL_INTEGRATION_REPLAY_V1_PASS"
    assert r["exchange_write_attempt_count"] == 0
    assert r["oos_consumed"] is False
    assert r["real_learning_claimed"] is False
