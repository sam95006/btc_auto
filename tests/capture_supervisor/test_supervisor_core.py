from __future__ import annotations

from backend.nexus_capture_supervisor.partition_accounting import account_partitions, scan_partition_tree
from backend.nexus_capture_supervisor.process_liveness import observe_process_liveness
from backend.nexus_capture_supervisor.recommendations import build_recommendations
from backend.nexus_capture_supervisor.storage_projection import project_disk
from backend.nexus_capture_supervisor.supervisor import CaptureIntegritySupervisor


def test_process_liveness_marks_dead_pids(synth_campaign):
    report = observe_process_liveness(
        runtime_root=synth_campaign["runtime"],
        campaign_id=synth_campaign["campaign_id"],
        launch={**synth_campaign["launch"], "status": "OK"},
        health={**synth_campaign["health"], "status": "OK", "checked_at": "2099-01-01T00:00:00Z"},
    )
    # Future checked_at avoids HEALTH_STALE; PIDs still dead.
    assert report["status"] == "DOWN"
    codes = {f["code"] for f in report["findings"]}
    assert "PROCESS_PARENT_DEAD" in codes


def test_partition_scan_and_hourly_gaps(synth_campaign):
    scan = scan_partition_tree(synth_campaign["partitions"])
    assert scan["status"] == "OK"
    assert len(scan["partitions"]) == 2
    acct = account_partitions(
        partitions_root=synth_campaign["partitions"],
        campaign_id=synth_campaign["campaign_id"],
        capture_start_utc="2026-08-05T09:42:05Z",
        expected_symbol_count=1,
    )
    assert acct["partition_count"] == 2
    assert acct["open_tail_count"] >= 1
    assert "20260805_09" in (acct.get("expected_hours") or []) or acct["hourly"]


def test_storage_floor_stop_required():
    report = project_disk(
        disk_root="D:\\",
        campaign_bytes=0,
        bytes_per_second=0.0,
        floor_bytes=10**18,
    )
    assert report["status"] == "STOP_REQUIRED"
    assert report["floor_ok"] is False


def test_recommendations_do_not_execute_stop():
    obs = {
        "storage": project_disk(disk_root="D:\\", campaign_bytes=0, bytes_per_second=0.0, floor_bytes=10**18),
        "process_liveness": {"findings": [], "status": "LIVE"},
        "ws_health": {"findings": []},
        "partition_accounting": {"findings": []},
        "clock_heartbeat": {"findings": []},
        "manifest_sampling": {"findings": []},
        "open_tail": {"findings": []},
        "duplicate_writer": {"findings": [], "status": "OK"},
    }
    rec = build_recommendations(observation=obs)
    assert rec["safe_stop_required"] is True
    assert rec["safe_stop_executed"] is False
    assert rec["restart_executed"] is False
    assert "supervisor_executes_live_stop" in rec["forbidden_actions"]


def test_supervisor_observe_readonly(synth_campaign):
    sup = CaptureIntegritySupervisor(
        runtime_root=synth_campaign["runtime"],
        capture_worktree=synth_campaign["worktree"],
        campaign_id=synth_campaign["campaign_id"],
        velocity_sample_seconds=0.0,
    )
    obs = sup.observe()
    assert obs["collector_modified"] is False
    assert obs["live_stop_executed"] is False
    assert obs["restart_executed"] is False
    assert obs["event_study_readiness_status"] == "NOT_READY"
    assert obs["exchange_write_attempt_count"] == 0
    assert obs["recommendations"]["safe_stop_executed"] is False
