"""Tests for Autonomous Closed-Loop Harness V1.1."""
from __future__ import annotations

import os
import threading

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_autonomy.closed_loop_harness_v1_1 import ClosedLoopHarnessV11, run_harness
from backend.nexus_autonomy.process_classification import (
    classify_completed_trade,
    control_fixture_process_evidence,
)


def test_bad_process_win_not_good_process_win():
    ev = control_fixture_process_evidence(bad=True)
    assert classify_completed_trade(pnl=5.0, process_evidence=ev) == "BAD_PROCESS_WIN"
    assert classify_completed_trade(pnl=-5.0, process_evidence=ev) == "BAD_PROCESS_LOSS"


def test_good_process_classes():
    ev = control_fixture_process_evidence(bad=False)
    assert classify_completed_trade(pnl=1.0, process_evidence=ev) == "GOOD_PROCESS_WIN"
    assert classify_completed_trade(pnl=-1.0, process_evidence=ev) == "GOOD_PROCESS_LOSS"


def test_undetermined_missing_evidence():
    assert classify_completed_trade(pnl=1.0, process_evidence={"note": "x"}) == "UNDETERMINED"


def test_cross_candidate_duplicate_closes_orphan():
    h = ClosedLoopHarnessV11()
    r1 = h.run_happy_path({"candidate_id": "C1", "idempotency_key": "SAME"}, pnl=1)
    r2 = h.run_happy_path({"candidate_id": "C2", "idempotency_key": "SAME"}, pnl=1)
    assert r1["status"] == "COMPLETE"
    assert r2["status"] == "DUPLICATE_IGNORED"
    assert r2["lifecycle_id"] == "C1"
    assert h.lifecycles["C2"].state == "CLOSED"
    assert h.orphan_lifecycle_count() == 0


def test_duplicate_after_completed():
    h = ClosedLoopHarnessV11()
    h.run_happy_path({"candidate_id": "D1", "idempotency_key": "K"}, pnl=1)
    r = h.run_happy_path({"candidate_id": "D2", "idempotency_key": "K"}, pnl=2)
    assert r["status"] == "DUPLICATE_IGNORED"


def test_concurrent_same_intent():
    h = ClosedLoopHarnessV11()
    results = []

    def go(cid: str) -> None:
        results.append(h.run_happy_path({"candidate_id": cid, "idempotency_key": "CONC"}, pnl=1))

    t1 = threading.Thread(target=go, args=("T1",))
    t2 = threading.Thread(target=go, args=("T2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    statuses = sorted(r["status"] for r in results)
    assert statuses == ["COMPLETE", "DUPLICATE_IGNORED"]
    assert h.orphan_lifecycle_count() == 0


def test_scenario_matrix_v1_1_pass():
    result = run_harness()
    assert result["recommendation"] == "NEXUS_AUTONOMOUS_HARNESS_V1_1_PASS"
    assert result["scenario_count"] >= 12
    assert result["scenario_failure_count"] == 0
    assert result["BAD_PROCESS_WIN_test_status"] == "PASS"
    assert result["UNDETERMINED_test_status"] == "PASS"
    assert result["cross_candidate_idempotency_status"] == "PASS"
    assert result["orphan_lifecycle_count"] == 0
    assert result["real_learning_claimed"] is False
    assert result["exchange_write_attempt_count"] == 0
