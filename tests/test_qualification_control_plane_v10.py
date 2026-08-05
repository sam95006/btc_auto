"""Tests for NEXUS_QUALIFICATION_CONTROL_PLANE_V10 — blocked-only control plane."""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

ROOT = Path(__file__).resolve().parents[1]

from backend.nexus_autonomy.qualification_blocked_stages_v10 import (
    BLOCKED_QUALIFICATION_STAGES_V10,
    HARD_BANS,
    STAGE_STATUS_BLOCKED,
    BlockedStageControllerV10,
    blocked_stage_matrix_document,
    default_blocked_stage_matrix,
)
from backend.nexus_autonomy.qualification_control_plane_v10 import (
    CONTROL_PLANE_STATUS,
    QUALIFICATION_STATUS_BLOCKED,
    SCHEMA_ID,
    QualificationControlPlaneV10,
    default_control_flags,
    run_qualification_control_plane_dry_run,
    write_immutable_artifacts,
)

OWNED_SOURCE_MODULES = (
    "backend/nexus_autonomy/qualification_control_plane_v10.py",
    "backend/nexus_autonomy/qualification_blocked_stages_v10.py",
    "tools/research/run_qualification_control_plane_v10.py",
)

SECRET_NEEDLES = (
    "API_KEY",
    "api_secret",
    "SECRET_KEY=",
    "BEGIN PRIVATE",
    "sk-",
    "gsk_",
)


def test_schema_and_qualification_status_blocked():
    summary = run_qualification_control_plane_dry_run()
    assert summary["schema"] == SCHEMA_ID
    assert summary["qualification_status"] == QUALIFICATION_STATUS_BLOCKED
    assert summary["control_plane_status"] == CONTROL_PLANE_STATUS
    assert summary["all_stages_blocked"] is True


def test_owned_stage_matrix_default_blocked():
    matrix = default_blocked_stage_matrix()
    required = {
        "CANDIDATE_FREEZE",
        "REPLAY",
        "WALK_FORWARD",
        "RISK_REVIEW",
        "OOS_RESERVATION",
        "DEMO_ELIGIBILITY",
    }
    assert set(BLOCKED_QUALIFICATION_STAGES_V10) == required
    assert list(matrix) == list(BLOCKED_QUALIFICATION_STAGES_V10)
    assert all(v == STAGE_STATUS_BLOCKED for v in matrix.values())

    summary = run_qualification_control_plane_dry_run()
    for stage in BLOCKED_QUALIFICATION_STAGES_V10:
        assert summary["stages"][stage] == STAGE_STATUS_BLOCKED


def test_control_flags_remain_false_zero():
    flags = default_control_flags()
    assert flags["Founder_authorization_present"] is False
    assert flags["founder_authorization_present"] is False
    assert flags["formal_walk_forward_executed"] is False
    assert flags["oos_reservation_created"] is False
    assert flags["oos_executed"] is False
    assert flags["strategy_selected"] is False
    assert flags["strategy_promoted"] is False
    assert flags["demo_order_count"] == 0
    assert flags["september_reserved_oos_consumed"] is False

    summary = run_qualification_control_plane_dry_run()
    assert summary["Founder_authorization_present"] is False
    assert summary["formal_walk_forward_executed"] is False
    assert summary["oos_reservation_created"] is False
    assert summary["oos_executed"] is False
    assert summary["strategy_selected"] is False
    assert summary["strategy_promoted"] is False
    assert summary["demo_order_count"] == 0
    assert summary["demo_eligibility"] is False
    assert summary["exchange_write_attempt_count"] == 0
    assert summary["september_reserved_oos_consumed"] is False


def test_stage_execute_attempts_all_refused():
    plane = QualificationControlPlaneV10()
    summary = plane.bootstrap_blocked()
    proofs = summary["proofs"]
    assert proofs["all_attempts_refused"] is True
    assert proofs["all_stages_blocked_after_attempts"] is True
    for stage in BLOCKED_QUALIFICATION_STAGES_V10:
        attempt = proofs["stage_execute_attempts"][stage]
        assert attempt["allowed"] is False
        assert attempt["executed"] is False
        assert attempt["status"] == STAGE_STATUS_BLOCKED
        assert summary["stages"][stage] == STAGE_STATUS_BLOCKED


def test_blocked_stage_controller_unknown_stage():
    ctrl = BlockedStageControllerV10()
    result = ctrl.attempt_execute_stage("NOT_A_REAL_STAGE")
    assert result["allowed"] is False
    assert result["executed"] is False
    assert result["reason"] == "UNKNOWN_STAGE"
    assert ctrl.all_blocked() is True


def test_hard_bans_include_september_oos():
    assert "no_september_reserved_oos_consumption" in HARD_BANS
    assert "no_walk_forward_execution" in HARD_BANS
    assert "no_demo_eligibility_grant" in HARD_BANS
    doc = blocked_stage_matrix_document()
    assert doc["all_stages_blocked"] is True
    assert "September" in doc["note"] or "OOS" in doc["note"]


def test_write_immutable_artifacts(tmp_path: Path):
    summary = run_qualification_control_plane_dry_run()
    paths = write_immutable_artifacts(summary, root=tmp_path)
    status = json.loads(paths["status"].read_text(encoding="utf-8"))
    assert status["schema"] == SCHEMA_ID
    assert status["qualification_status"] == QUALIFICATION_STATUS_BLOCKED
    assert status["Founder_authorization_present"] is False
    assert status["formal_walk_forward_executed"] is False
    assert status["oos_reservation_created"] is False
    assert status["oos_executed"] is False
    assert status["strategy_selected"] is False
    assert status["strategy_promoted"] is False
    assert status["demo_order_count"] == 0

    stages = json.loads(paths["stages"].read_text(encoding="utf-8"))
    assert all(v == STAGE_STATUS_BLOCKED for v in stages["stages"].values())
    assert stages["all_stages_blocked"] is True

    flags = json.loads(paths["flags"].read_text(encoding="utf-8"))
    assert flags["demo_order_count"] == 0
    assert flags["september_reserved_oos_consumed"] is False


def test_secret_scan_owned_modules():
    for rel in OWNED_SOURCE_MODULES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for needle in SECRET_NEEDLES:
            assert needle not in text, f"{rel} contains secret needle {needle!r}"
        assert "api.bybit.com" not in text
        assert "api.binance.com" not in text
