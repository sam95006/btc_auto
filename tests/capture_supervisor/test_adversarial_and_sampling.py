from __future__ import annotations

import json
from pathlib import Path

from backend.nexus_capture_supervisor.adversarial import run_adversarial_pass2
from backend.nexus_capture_supervisor.constants import OWNED_PATHS
from backend.nexus_capture_supervisor.duplicate_writer import detect_duplicate_writers
from backend.nexus_capture_supervisor.manifest_sampling import sample_manifests_and_checksums
from backend.nexus_capture_supervisor.open_tail import account_open_tails
from backend.nexus_capture_supervisor.secret_scan import secret_scan


def test_open_tail_accounting(synth_campaign):
    report = account_open_tails(
        partitions_root=synth_campaign["partitions"],
        campaign_id=synth_campaign["campaign_id"],
    )
    assert report["open_tail_count"] >= 1
    assert report["policy"]["mutate_open_tails"] is False
    assert report["policy"]["rewrite_raw"] is False


def test_manifest_sampling(synth_campaign):
    report = sample_manifests_and_checksums(
        partitions_root=synth_campaign["partitions"],
        campaign_id=synth_campaign["campaign_id"],
        sample_max=8,
    )
    assert report["partition_count"] == 2
    assert report["sample_size"] >= 1
    assert report.get("silent_fallback") is False


def test_duplicate_writer_single_session(synth_campaign):
    report = detect_duplicate_writers(
        runtime_root=synth_campaign["runtime"],
        campaign_id=synth_campaign["campaign_id"],
        partitions_root=synth_campaign["partitions"],
        launch={**synth_campaign["launch"], "status": "OK"},
        health={**synth_campaign["health"], "status": "OK"},
    )
    assert report["session_count"] == 1
    assert report["duplicate_partition_id_count"] == 0


def test_adversarial_pass2(tmp_path, synth_campaign):
    pass1 = {
        "evidence_class": "REAL_LIVE_CAMPAIGN_READONLY",
        "observation": {
            "event_study_readiness_status": "NOT_READY",
            "event_study_real_execution": False,
            "exchange_write_attempt_count": 0,
            "live_stop_executed": False,
            "restart_executed": False,
            "collector_modified": False,
            "ops_role": "observe_recommend_only",
            "hard_bans": list(
                __import__(
                    "backend.nexus_capture_supervisor.constants", fromlist=["HARD_BANS"]
                ).HARD_BANS
            ),
            "path_meta": {"live_capture_started": True},
            "partition_accounting": {"missing_hours": [], "findings": []},
        },
    }
    changed = [f"{p}/x.py" if not p.endswith("/") else f"{p}x.py" for p in OWNED_PATHS[:1]]
    # Use real owned path style
    changed = ["backend/nexus_capture_supervisor/constants.py"]
    report = run_adversarial_pass2(
        repo_root=Path(__file__).resolve().parents[2],
        work_root=tmp_path / "adv",
        pass1=pass1,
        changed_files=changed,
    )
    assert report["all_passed"] is True
    assert all(t["status"] == "PASS" for t in report["negative_tests"])


def test_secret_scan_clean_on_package():
    root = Path(__file__).resolve().parents[2]
    report = secret_scan(root)
    assert report["secret_leak_count"] == 0
