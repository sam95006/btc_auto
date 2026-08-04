"""Synthetic-fixture tests for microstructure campaign finalizer V1."""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_microstructure.campaign_finalizer_fixtures_v1 import (
    build_clean_campaign_fixture,
    build_degraded_campaign_fixture,
)
from backend.nexus_microstructure.campaign_finalizer_v1 import (
    EVENT_STUDY_HOLD_GATES,
    evaluate_event_study_readiness,
    finalize_campaign,
    replay_partition_checksum,
    score_clock_quality,
    score_heartbeat_quality,
    score_memory_quality,
    write_immutable_status_package,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "microstructure_finalizer"


def test_clean_campaign_finalization(tmp_path: Path):
    root = build_clean_campaign_fixture(tmp_path / "clean")
    report = finalize_campaign(root)
    status = report["finalizer_status"]
    audit = report["data_quality_audit"]

    assert status["Microstructure_Finalizer_status"] == "PASS"
    assert status["clean_campaign_finalization"] is True
    assert status["synthetic_fixtures_only"] is True
    assert status["live_campaign_interfered"] is False
    assert status["event_study_readiness_status"] == "NOT_READY"
    assert status["event_study_real_execution"] is False
    assert status["new_strategy_generated_count"] == 0
    assert status["profitability_claim_count"] == 0

    assert audit["valid_capture_seconds"] == 4200
    assert audit["valid_capture_hours"] == 4200 / 3600.0
    assert audit["connection_gap_seconds"] == 120
    assert audit["wall_elapsed_seconds"] == 4500
    # Never equate wall clock with valid capture depth.
    assert audit["valid_capture_seconds"] < audit["wall_elapsed_seconds"]

    assert audit["complete_UTC_hours"] >= 1
    assert audit["partial_UTC_hours"] >= 1
    assert set(audit["symbol_coverage"]) == {"BTCUSDT", "ETHUSDT"}
    assert audit["symbol_count"] == 2

    assert audit["clock_quality"] == "GOOD"
    assert audit["heartbeat_quality"] == "GOOD"
    assert audit["memory_quality"] == "GOOD"

    assert audit["checksum_replay"]["checksum_replay_verified"] is True
    assert audit["partition_completeness"]["partition_completeness_status"] == "COMPLETE"
    assert audit["truncated_tail_detection"]["truncated_tail_detected"] is False
    assert audit["cross_partition_linkage"]["cross_partition_linkage_status"] == "PASS"
    assert audit["storage_cap"]["storage_cap_outcome"] == "WITHIN_CAPS"
    assert audit["campaign_resume_metadata"]["resumable"] is True
    assert audit["campaign_resume_metadata"]["clean_shutdown"] is True
    assert audit["integrity_status"] == "PASS"

    readiness = report["event_study_readiness"]
    assert readiness["event_study_readiness_status"] == "NOT_READY"
    assert "calendar_days" in readiness["blockers"]
    assert EVENT_STUDY_HOLD_GATES["calendar_days"] == 14


def test_degraded_fixture_detects_truncation_linkage_and_caps(tmp_path: Path):
    root = build_degraded_campaign_fixture(tmp_path / "degraded")
    report = finalize_campaign(root)
    status = report["finalizer_status"]
    audit = report["data_quality_audit"]

    assert status["Microstructure_Finalizer_status"] == "FAIL"
    assert status["event_study_readiness_status"] == "NOT_READY"
    assert audit["truncated_tail_detection"]["truncated_tail_detected"] is True
    assert audit["checksum_replay"]["checksum_replay_verified"] is False
    assert audit["cross_partition_linkage"]["cross_partition_linkage_status"] == "FAIL"
    assert audit["storage_cap"]["storage_cap_outcome"] == "HARD_CAP_HIT"
    assert audit["clock_quality"] == "POOR"
    assert audit["heartbeat_quality"] == "POOR"
    assert audit["memory_quality"] == "POOR"
    assert "truncated_tail_partitions_present" in status["critical_findings"]
    assert "cross_partition_linkage_breaks" in status["critical_findings"]
    assert audit["campaign_resume_metadata"]["clean_shutdown"] is False


def test_quality_scorers_thresholds():
    assert score_clock_quality({"server_clock_sample_count": 5, "local_minus_server_clock_offset_ms_p95": 10})[
        "clock_quality"
    ] == "GOOD"
    assert score_clock_quality({"server_clock_sample_count": 5, "local_minus_server_clock_offset_ms_p95": 100})[
        "clock_quality"
    ] == "ACCEPTABLE"
    assert score_heartbeat_quality({"heartbeat_status": "HEARTBEAT_VERIFIED"})["heartbeat_quality"] == "GOOD"
    assert score_memory_quality({"memory_growth_status": "STABLE"})["memory_quality"] == "GOOD"
    assert score_memory_quality({"memory_growth_status": "LINEAR_GROWTH_DETECTED"})["memory_quality"] == "POOR"


def test_event_study_readiness_stays_not_ready_without_gates():
    r = evaluate_event_study_readiness(
        {
            "calendar_days": 2,
            "complete_UTC_day_coverage": False,
            "symbol_diversity": 2,
            "liquidation_event_count": 8,
            "integrity_status": "PASS",
            "Founder_authorization": False,
        }
    )
    assert r["event_study_readiness_status"] == "NOT_READY"
    assert r["event_study_real_execution"] is False
    assert "calendar_days" in r["blockers"]
    assert "Founder_authorization" in r["blockers"]


def test_event_study_ready_only_when_all_gates_met():
    r = evaluate_event_study_readiness(
        {
            "calendar_days": 14,
            "complete_UTC_day_coverage": True,
            "symbol_diversity": 25,
            "liquidation_event_count": 500,
            "integrity_status": "PASS",
            "Founder_authorization": True,
        }
    )
    assert r["event_study_readiness_status"] == "READY"
    assert r["blockers"] == []


def test_committed_fixture_roundtrip():
    clean = FIXTURES / "clean_campaign"
    assert (clean / "campaign_meta.json").is_file()
    report = finalize_campaign(clean)
    assert report["finalizer_status"]["event_study_readiness_status"] == "NOT_READY"
    assert report["finalizer_status"]["checksum_replay_verified"] is True


def test_write_immutable_status_package(tmp_path: Path):
    root = build_clean_campaign_fixture(tmp_path / "pkg_src")
    out = tmp_path / "immutable"
    report = write_immutable_status_package(root, out)
    assert (out / "finalizer_status.json").is_file()
    assert (out / "data_quality_audit.json").is_file()
    assert (out / "event_study_readiness.json").is_file()
    assert (out / "campaign_finalize_report.json").is_file()
    readiness = json.loads((out / "event_study_readiness.json").read_text(encoding="utf-8"))
    assert readiness["event_study_readiness_status"] == "NOT_READY"
    assert report["finalizer_status"]["event_study_readiness_status"] == "NOT_READY"


def test_replay_detects_missing_file(tmp_path: Path):
    r = replay_partition_checksum(tmp_path / "nope.jsonl.gz")
    assert r["integrity_status"] == "MISSING"
