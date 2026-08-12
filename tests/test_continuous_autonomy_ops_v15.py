"""Tests for V15-J Continuous Autonomy Operations Control."""
from __future__ import annotations

import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["DEMO"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_autonomy.continuous_ops_control_v15.adversarial import (
    PASS2_RUNNERS,
    run_pass2,
)
from backend.nexus_autonomy.continuous_ops_control_v15.constants import (
    MUTATING_OPS,
    PROOF_IDS_PASS1,
    PROOF_IDS_PASS2,
    READ_OPS,
)
from backend.nexus_autonomy.continuous_ops_control_v15.control_plane import (
    ContinuousAutonomyOpsControlV15,
)
from backend.nexus_autonomy.continuous_ops_control_v15.proofs import (
    PROOF_RUNNERS,
    run_pass1,
)


def test_proof_runners_registered():
    assert set(PROOF_IDS_PASS1) == set(PROOF_RUNNERS)
    assert set(PROOF_IDS_PASS2) == set(PASS2_RUNNERS)
    assert len(MUTATING_OPS) == 6
    assert len(READ_OPS) == 9


def test_start_pause_resume_safe_stop(tmp_path: Path):
    ctrl = ContinuousAutonomyOpsControlV15(tmp_path / "ops")
    try:
        p = ctrl.issue_founder_proof(op="start", idempotency_key="t-start")
        r = ctrl.mutate(
            "start",
            idempotency_key="t-start",
            founder_proof=p,
            payload={"session_id": "test-sess"},
        )
        assert r["status"] == "PASS"
        assert r["state_after"] == "RUNNING"
        assert r["founder_authorization_present"] is True
        assert r["ledger"]["event_id"]
        assert r["checkpoint"]["count"] >= 1

        p2 = ctrl.issue_founder_proof(op="pause", idempotency_key="t-pause")
        assert (
            ctrl.mutate("pause", idempotency_key="t-pause", founder_proof=p2)["state_after"]
            == "PAUSED"
        )
        p3 = ctrl.issue_founder_proof(op="resume", idempotency_key="t-resume")
        assert (
            ctrl.mutate("resume", idempotency_key="t-resume", founder_proof=p3)[
                "state_after"
            ]
            == "RUNNING"
        )
        p4 = ctrl.issue_founder_proof(op="safe_stop", idempotency_key="t-stop")
        assert (
            ctrl.mutate("safe_stop", idempotency_key="t-stop", founder_proof=p4)[
                "state_after"
            ]
            == "STOPPED"
        )
    finally:
        ctrl.close()


def test_missing_auth_denied(tmp_path: Path):
    ctrl = ContinuousAutonomyOpsControlV15(tmp_path / "deny")
    try:
        r = ctrl.mutate(
            "start",
            idempotency_key="d1",
            founder_proof=None,
            payload={"session_id": "x"},
        )
        assert r["status"] == "DENIED"
    finally:
        ctrl.close()


def test_idempotency(tmp_path: Path):
    ctrl = ContinuousAutonomyOpsControlV15(tmp_path / "idem")
    try:
        p = ctrl.issue_founder_proof(op="start", idempotency_key="idem")
        a = ctrl.mutate(
            "start",
            idempotency_key="idem",
            founder_proof=p,
            payload={"session_id": "idem-sess"},
        )
        b = ctrl.mutate(
            "start",
            idempotency_key="idem",
            founder_proof=None,
            payload={"session_id": "idem-sess"},
        )
        assert a["status"] == "PASS"
        assert b["status"] == "DUPLICATE_IGNORED"
        assert b["duplicate"] is True
    finally:
        ctrl.close()


def test_kill_and_exchange_ban(tmp_path: Path):
    ctrl = ContinuousAutonomyOpsControlV15(tmp_path / "kill")
    try:
        p = ctrl.issue_founder_proof(op="start", idempotency_key="k-start")
        ctrl.mutate(
            "start",
            idempotency_key="k-start",
            founder_proof=p,
            payload={"session_id": "k"},
        )
        pk = ctrl.issue_founder_proof(op="kill", idempotency_key="k-kill")
        kr = ctrl.mutate(
            "kill", idempotency_key="k-kill", founder_proof=pk, payload={"reason": "t"}
        )
        assert kr["state_after"] == "KILLED"
        x = ctrl.attempt_exchange_write(exchange_write=True)
        assert x["status"] == "DENIED"
        assert x["exchange_write_attempt_count"] >= 1
        assert x["demo_order_count"] == 0
    finally:
        ctrl.close()


def test_read_blocks(tmp_path: Path):
    ctrl = ContinuousAutonomyOpsControlV15(tmp_path / "reads")
    try:
        p = ctrl.issue_founder_proof(op="start", idempotency_key="r-start")
        ctrl.mutate(
            "start",
            idempotency_key="r-start",
            founder_proof=p,
            payload={"session_id": "r"},
        )
        for name in READ_OPS:
            block = ctrl.read(name)
            assert block.get("read_only") is True
            assert block.get("exchange_write") is False
        qb = ctrl.read("qualification_blocks")
        assert qb["all_blocked"] is True
        adv = ctrl.attempt_qualification_advance("walk_forward")
        assert adv["status"] == "DENIED"
        assert adv["executed"] is False
    finally:
        ctrl.close()


def test_pass1_matrix(tmp_path: Path):
    report = run_pass1(tmp_path / "pass1")
    assert report["overall_status"] == "PASS", report.get("failed")
    assert report["proofs_passed"] == len(PROOF_IDS_PASS1)


def test_pass2_matrix(tmp_path: Path):
    art = tmp_path / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    (art / "readiness_summary.json").write_text("{}", encoding="utf-8")
    report = run_pass2(tmp_path / "pass2", artifact_dir=art)
    assert report["overall_status"] == "PASS", report.get("failed")
    assert report["proofs_passed"] == len(PROOF_IDS_PASS2)
