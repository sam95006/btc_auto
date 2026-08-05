"""Tests for Microstructure Operations V10 (Lane D)."""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

import pytest

from backend.nexus_microstructure.campaign_scheduler_v10 import CampaignSchedulerV10
from backend.nexus_microstructure.ops_v10.gates import evaluate_capture_start_gates
from backend.nexus_microstructure.ops_v10.integrity_scoring import score_campaign_integrity
from backend.nexus_microstructure.ops_v10.registry import CampaignRegistryV10
from backend.nexus_microstructure.ops_v10.resume import BoundedResumeController
from backend.nexus_microstructure.ops_v10.retention import retention_dry_run_v10
from backend.nexus_microstructure.ops_v10.safe_stop import AutomaticSafeStop
from backend.nexus_microstructure.storage_budget_v10 import (
    DEFAULT_HARD_CAP_BYTES,
    DEFAULT_SOFT_CAP_BYTES,
    GIB,
    StorageBudgetControllerV10,
    check_minimum_free_disk,
)

REPO = Path(__file__).resolve().parents[1]
REAL_FINALIZER = (
    REPO / "artifacts/readiness/immutable/microstructure_campaign_finalizer_v1_real_ms_accum_v7"
)


def _free_pass(**extra):
    return {
        "schema": "minimum_free_disk_controller_v10",
        "path": "D:\\",
        "free_bytes": 40 * GIB,
        "free_gib": 40.0,
        "minimum_free_disk_bytes": 30 * GIB,
        "minimum_free_disk_gib": 30.0,
        "status": "PASS",
        "passed": True,
        **extra,
    }


def _free_fail(**extra):
    return {
        "schema": "minimum_free_disk_controller_v10",
        "path": "D:\\",
        "free_bytes": 5 * GIB,
        "free_gib": 5.0,
        "minimum_free_disk_bytes": 30 * GIB,
        "minimum_free_disk_gib": 30.0,
        "status": "FAIL",
        "passed": False,
        **extra,
    }


def test_storage_budget_caps_and_hard_stop():
    ctl = StorageBudgetControllerV10(
        soft_limit_bytes=1000,
        hard_limit_bytes=2000,
        minimum_free_disk_bytes=30 * GIB,
        disk_root="D:\\",
    )
    assert ctl.storage_cap_configured is True
    assert ctl.observe_write(compressed_delta=900) == "NORMAL"
    assert ctl.observe_write(compressed_delta=200) == "DEGRADED_STORAGE_MODE"
    assert ctl.observe_write(compressed_delta=1000) == "STORAGE_BUDGET_BLOCKED"
    assert ctl.stop_requested is True
    assert ctl.stop_reason == "hard_storage_cap"
    report = ctl.report()
    assert report["storage_tree_scanned_per_event"] is False
    assert report["deletion_executed"] is False


def test_storage_budget_requires_positive_caps():
    with pytest.raises(ValueError):
        StorageBudgetControllerV10(soft_limit_bytes=0, hard_limit_bytes=100)
    with pytest.raises(ValueError):
        StorageBudgetControllerV10(soft_limit_bytes=200, hard_limit_bytes=100)


def test_minimum_free_disk_controller_live_probe():
    r = check_minimum_free_disk("D:\\", minimum_free_disk_bytes=30 * GIB)
    assert r["status"] in {"PASS", "FAIL"}
    assert "free_bytes" in r
    assert r["minimum_free_disk_bytes"] == 30 * GIB


def test_capture_gates_block_when_disk_low():
    g = evaluate_capture_start_gates(
        previous_campaign_finalized=True,
        storage_cap_configured=True,
        enable_live_capture=False,
        free_disk_override=_free_fail(),
    )
    assert g["decision"] == "BLOCK_START"
    assert "d_free_space_ge_30_gib" in g["blockers"]
    assert g["live_capture_started"] is False
    assert g["event_study_readiness_status"] == "NOT_READY"


def test_capture_gates_block_when_not_finalized():
    g = evaluate_capture_start_gates(
        previous_campaign_finalized=False,
        storage_cap_configured=True,
        free_disk_override=_free_pass(),
    )
    assert g["decision"] == "BLOCK_START"
    assert "previous_campaign_finalized" in g["blockers"]


def test_capture_gates_block_when_caps_missing():
    g = evaluate_capture_start_gates(
        previous_campaign_finalized=True,
        storage_cap_configured=False,
        free_disk_override=_free_pass(),
    )
    assert g["decision"] == "BLOCK_START"
    assert "storage_cap_configured" in g["blockers"]


def test_capture_gates_dry_run_when_all_pass():
    g = evaluate_capture_start_gates(
        previous_campaign_finalized=True,
        storage_cap_configured=True,
        enable_live_capture=False,
        free_disk_override=_free_pass(),
    )
    assert g["decision"] == "DRY_RUN_ONLY"
    assert g["all_hard_gates_passed"] is True
    assert g["live_capture_would_start"] is False


def test_capture_gates_allow_only_with_explicit_flag():
    g = evaluate_capture_start_gates(
        previous_campaign_finalized=True,
        storage_cap_configured=True,
        enable_live_capture=True,
        free_disk_override=_free_pass(),
    )
    assert g["decision"] == "ALLOW_START"
    assert g["live_capture_started"] is False  # gate decision is not a start


def test_registry_and_finalized_flag(tmp_path: Path):
    reg = CampaignRegistryV10(tmp_path / "registry.json")
    reg.register_campaign("c1", soft_storage_cap_bytes=DEFAULT_SOFT_CAP_BYTES, hard_storage_cap_bytes=DEFAULT_HARD_CAP_BYTES)
    assert reg.previous_campaign_finalized("c1") is False
    reg.mark_finalized("c1", finalizer_status="FAIL", integrity_status="FAIL")
    assert reg.previous_campaign_finalized("c1") is True
    snap = reg.snapshot()
    assert snap["event_study_readiness_status"] == "NOT_READY"
    assert snap["campaigns"]["c1"]["event_study_readiness_status"] == "NOT_READY"


def test_bounded_resume_honors_non_resumable():
    ctl = BoundedResumeController(campaign_id="ms_accum_v7_bounded_24h")
    cp = ctl.from_finalizer_resume_metadata(
        {
            "resumable": False,
            "clean_shutdown": None,
            "capture_session_ids": ["ms12_ACCUM24_1785856716"],
            "last_partition_id": None,
        }
    )
    assert cp["resumable"] is False
    decision = ctl.allow_bounded_resume()
    assert decision["allow_bounded_resume"] is False
    assert decision["live_capture_started"] is False


def test_retention_dry_run_never_deletes(tmp_path: Path):
    gz = tmp_path / "AGGRESSIVE_TRADE_FLOW" / "part.jsonl.gz"
    gz.parent.mkdir(parents=True)
    gz.write_bytes(b"\x1f\x8b" + b"\x00" * 20)
    report = retention_dry_run_v10(tmp_path)
    assert report["dry_run"] is True
    assert report["deletion_executed"] is False
    assert report["retention_candidate_partition_count"] == 1


def test_integrity_scoring_from_fail_status():
    score = score_campaign_integrity(
        finalizer_status={
            "checksum_replay_verified": False,
            "truncated_tail_detected": True,
            "cross_partition_linkage_status": "FAIL",
            "partition_completeness_status": "PARTIAL",
            "storage_cap_outcome": "WITHIN_CAPS",
            "integrity_status": "FAIL",
        }
    )
    assert score["integrity_overall"] == "FAIL"
    assert score["integrity_score"] < 60
    assert score["event_study_readiness_status"] == "NOT_READY"


def test_automatic_safe_stop_on_disk_fail():
    stop = AutomaticSafeStop()
    ev = stop.evaluate(
        budget_report={
            "stop_requested": True,
            "stop_reason": "minimum_free_disk_fail",
            "mode": "STORAGE_BUDGET_BLOCKED",
            "minimum_free_disk": _free_fail(),
        },
        storage_cap_configured=True,
        previous_campaign_finalized=True,
    )
    assert ev["safe_stop_required"] is True
    assert "minimum_free_disk_fail" in ev["reasons"]
    assert ev["exchange_write_attempt_count"] == 0
    policy = stop.policy()
    assert "event_study_start" in policy["forbidden_actions"]


def test_scheduler_integrates_real_finalizer_dry_run(tmp_path: Path):
    assert (REAL_FINALIZER / "finalizer_status.json").is_file()
    status = json.loads((REAL_FINALIZER / "finalizer_status.json").read_text(encoding="utf-8"))
    assert status["campaign_id"] == "ms_accum_v7_bounded_24h"
    assert status["event_study_readiness_status"] == "NOT_READY"

    sched = CampaignSchedulerV10(
        REPO,
        registry_path=tmp_path / "registry.json",
        disk_root="D:\\",
        previous_campaign_id="ms_accum_v7_bounded_24h",
    )
    cycle = sched.run_controller_cycle(
        proposed_campaign_id="ms_accum_v10_test",
        enable_live_capture=False,
        partitions_root=tmp_path / "parts",
        free_disk_override=_free_pass(),
    )
    assert cycle["live_capture_started"] is False
    assert cycle["event_study_readiness_status"] == "NOT_READY"
    assert cycle["event_study_real_execution"] is False
    assert cycle["new_strategy_generated_count"] == 0
    assert cycle["finalizer_integration"]["previous_campaign_finalized"] is True
    assert cycle["capture_start_gates"]["decision"] == "DRY_RUN_ONLY"
    assert cycle["segment_plan"]["action"] == "DRY_RUN_CONTROLLER_ONLY"
    assert cycle["integrity_score"]["integrity_status"] == "FAIL"
    readiness = json.loads((REAL_FINALIZER / "event_study_readiness.json").read_text(encoding="utf-8"))
    assert readiness["event_study_readiness_status"] == "NOT_READY"


def test_scheduler_blocks_when_disk_gate_fails(tmp_path: Path):
    sched = CampaignSchedulerV10(
        REPO,
        registry_path=tmp_path / "registry.json",
        previous_campaign_id="ms_accum_v7_bounded_24h",
    )
    cycle = sched.run_controller_cycle(
        proposed_campaign_id="ms_accum_v10_blocked",
        enable_live_capture=True,
        free_disk_override=_free_fail(),
    )
    assert cycle["capture_start_gates"]["decision"] == "BLOCK_START"
    assert cycle["live_capture_started"] is False
    assert cycle["segment_plan"]["action"] == "BLOCKED"


def test_scheduler_authorize_not_start_when_gates_and_flag(tmp_path: Path):
    sched = CampaignSchedulerV10(
        REPO,
        registry_path=tmp_path / "registry.json",
        previous_campaign_id="ms_accum_v7_bounded_24h",
    )
    cycle = sched.run_controller_cycle(
        proposed_campaign_id="ms_accum_v10_auth",
        enable_live_capture=True,
        free_disk_override=_free_pass(),
    )
    assert cycle["capture_start_gates"]["decision"] == "ALLOW_START"
    assert cycle["live_capture_started"] is False
    assert cycle["segment_plan"]["action"] == "LIVE_CAPTURE_AUTHORIZED_NOT_STARTED"


def test_runner_writes_artifacts(tmp_path: Path, monkeypatch):
    import tools.research.run_microstructure_operations_v10 as runner

    out = tmp_path / "artifacts"
    # Point registry to tmp via monkeypatch of CampaignSchedulerV10? Use argv artifact-dir only;
    # scheduler still writes to repo runtime — instead call write_artifacts + cycle via scheduler on tmp registry.
    sched = CampaignSchedulerV10(
        REPO,
        registry_path=tmp_path / "registry.json",
        previous_campaign_id="ms_accum_v7_bounded_24h",
    )
    cycle = sched.run_controller_cycle(
        enable_live_capture=False,
        free_disk_override=_free_pass(),
        partitions_root=tmp_path / "parts",
    )
    secret = {"secret_leak_count": 0, "secret_leak_paths": []}
    runner.write_artifacts(out, cycle, secret)
    assert (out / "operations_status.json").is_file()
    assert (out / "event_study_readiness.json").is_file()
    ops = json.loads((out / "operations_status.json").read_text(encoding="utf-8"))
    ready = json.loads((out / "event_study_readiness.json").read_text(encoding="utf-8"))
    assert ops["event_study_readiness_status"] == "NOT_READY"
    assert ready["event_study_readiness_status"] == "NOT_READY"
    assert ops["live_capture_started"] is False
    assert ops["deletion_executed"] is False
