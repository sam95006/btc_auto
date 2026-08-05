"""Founder R2 adversarial tests — durability + microstructure cross-lane review."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("EXCHANGE_WRITE", "false")

from tools.review.r2_durability_microstructure.adversarial_matrix import (
    ADVERSARIAL_SCENARIOS,
    SCENARIO_RUNNERS,
    run_adversarial_matrix,
    scenario_checkpoint_before_ledger_fsync,
    scenario_clock_rollback_across_partition_rotation,
    scenario_clock_rollback_lost_on_reopen,
    scenario_concurrent_snapshot_wal_lock,
    scenario_duplicate_partition_identity,
    scenario_fsync_interrupt_commits_anyway,
    scenario_manifest_before_file_close,
    scenario_missing_previous_link,
    scenario_orphan_open_marker_after_finalize,
    scenario_partition_migrated_while_open,
    scenario_power_loss_during_gzip_close,
    scenario_restore_from_corrupted_lkg,
    scenario_snapshot_from_stale_ledger_tail,
    scenario_snapshot_skips_payload_corruption,
)
from tools.review.r2_durability_microstructure.findings import (
    STATIC_FINDINGS,
    build_findings_report,
    integration_recommendation,
)


REQUIRED_FOUNDER_SCENARIOS = {
    "power_loss_during_gzip_close",
    "checkpoint_before_ledger_fsync",
    "snapshot_from_stale_ledger_tail",
    "manifest_before_file_close",
    "partition_migrated_while_open",
    "duplicate_partition_identity",
    "missing_previous_link",
    "clock_rollback_across_partition_rotation",
    "restore_from_corrupted_lkg",
}


def test_required_founder_scenarios_registered():
    assert REQUIRED_FOUNDER_SCENARIOS.issubset(set(ADVERSARIAL_SCENARIOS))
    for sid in REQUIRED_FOUNDER_SCENARIOS:
        assert sid in SCENARIO_RUNNERS


def test_power_loss_during_gzip_close(tmp_path: Path):
    r = scenario_power_loss_during_gzip_close(tmp_path)
    assert r.control_ok is True  # classic kill path classified
    assert r.hazard_confirmed is True  # post-gzip-close interrupt gap
    assert r.evidence["kill_before_footer"]["is_open_tail"] is True


def test_checkpoint_before_ledger_fsync(tmp_path: Path):
    r = scenario_checkpoint_before_ledger_fsync(tmp_path)
    assert r.hazard_confirmed is True
    assert r.evidence["premature_checkpoint_without_lkg"] is True


def test_snapshot_from_stale_ledger_tail(tmp_path: Path):
    r = scenario_snapshot_from_stale_ledger_tail(tmp_path)
    assert r.hazard_confirmed is True
    assert r.severity_if_confirmed == "CRITICAL"
    assert r.evidence["mismatch"] is True
    assert r.evidence["claimed_source_ledger_position"] > r.evidence["checksummed_main_file_event_count"]


def test_manifest_before_file_close_control(tmp_path: Path):
    r = scenario_manifest_before_file_close(tmp_path)
    assert r.hazard_confirmed is False
    assert r.control_ok is True
    assert r.evidence["observed_order"][0] == "before_gzip_close"
    assert "after_gzip_close" in r.evidence["observed_order"]
    assert r.evidence["observed_order"].index("after_gzip_close") < r.evidence["observed_order"].index(
        "before_manifest"
    )


def test_partition_migrated_while_open(tmp_path: Path):
    r = scenario_partition_migrated_while_open(tmp_path)
    assert r.control_ok is True
    assert r.hazard_confirmed is True  # no migration gate
    assert r.evidence["storage_gate_blocks_open_migration"] is False


def test_duplicate_partition_identity(tmp_path: Path):
    r = scenario_duplicate_partition_identity(tmp_path)
    assert r.hazard_confirmed is True
    assert r.evidence["gz_file_count"] == 1


def test_missing_previous_link_control(tmp_path: Path):
    r = scenario_missing_previous_link(tmp_path)
    assert r.control_ok is True
    assert r.hazard_confirmed is False


def test_clock_rollback_across_partition_rotation(tmp_path: Path):
    r = scenario_clock_rollback_across_partition_rotation(tmp_path)
    assert r.hazard_confirmed is True
    assert r.evidence["linkage"]["status"] == "FAIL"


def test_restore_from_corrupted_lkg_control(tmp_path: Path):
    r = scenario_restore_from_corrupted_lkg(tmp_path)
    assert r.control_ok is True
    assert r.hazard_confirmed is False
    assert r.evidence["restore_status"] == "CORRUPTION_DETECTED"


def test_snapshot_skips_payload_corruption(tmp_path: Path):
    r = scenario_snapshot_skips_payload_corruption(tmp_path)
    assert r.hazard_confirmed is True
    assert r.evidence["snapshot_status"] == "SNAPSHOT_OK"
    assert r.evidence["detect_corruption"] == "CORRUPTION_DETECTED"


def test_clock_rollback_lost_on_reopen(tmp_path: Path):
    r = scenario_clock_rollback_lost_on_reopen(tmp_path)
    assert r.hazard_confirmed is True
    assert r.evidence["second_after_reopen"] == "APPENDED"


def test_fsync_interrupt_commits_anyway(tmp_path: Path):
    r = scenario_fsync_interrupt_commits_anyway(tmp_path)
    assert r.hazard_confirmed is True
    assert r.evidence["event_count_after"] == 2


def test_orphan_open_marker_after_finalize(tmp_path: Path):
    r = scenario_orphan_open_marker_after_finalize(tmp_path)
    assert r.hazard_confirmed is True
    assert r.evidence["finding_count"] == 0


def test_concurrent_snapshot_wal_lock(tmp_path: Path):
    r = scenario_concurrent_snapshot_wal_lock(tmp_path)
    # Windows commonly confirms PermissionError; other platforms may not — still must run cleanly
    assert r.scenario_id == "concurrent_snapshot_wal_lock"
    assert "error" in r.evidence or "snap" in r.evidence


def test_full_matrix_two_passes(tmp_path: Path):
    p1 = run_adversarial_matrix(base_root=tmp_path / "p1", pass_id="PASS_1")
    p2 = run_adversarial_matrix(base_root=tmp_path / "p2", pass_id="PASS_2")
    assert p1["total_scenarios"] == len(ADVERSARIAL_SCENARIOS)
    assert p2["total_scenarios"] == len(ADVERSARIAL_SCENARIOS)
    assert p1["hazard_confirmed_count"] >= 8
    assert p2["raw_campaign_evidence_modified"] is False

    report = build_findings_report(matrix_pass1=p1, matrix_pass2=p2)
    assert len(report["critical_findings"]) >= 3
    assert report["integration_recommendation"]["integration_recommendation"].startswith(
        "DO_NOT_INTEGRATE"
    )
    assert report["raw_campaign_evidence_modified"] is False


def test_static_findings_cover_authority_surfaces():
    areas = {f["area"] for f in STATIC_FINDINGS}
    for needle in (
        "snapshot_authority",
        "checkpoint_authority",
        "open-tail_semantics",
        "cross-partition_linkage",
        "migration_provenance",
        "storage_safety",
    ):
        assert any(needle in a for a in areas), needle


def test_integration_recommendation_blocks_on_critical():
    fake_matrix = {"hazard_confirmed_count": 9, "pass_id": "PASS_2"}
    rec = integration_recommendation(STATIC_FINDINGS, fake_matrix)
    assert rec["integration_recommendation"] == "DO_NOT_INTEGRATE_AS_AUTHORITY_UNTIL_CRITICAL_FIXED"
    assert "R2-C-001" in rec["blocking_finding_ids"]


def test_review_runner_writes_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import sys

    from tools.review.r2_durability_microstructure import run_r2_review

    out = tmp_path / "artifacts"
    monkeypatch.setattr(sys, "argv", ["run_r2_review.py", "--output-dir", str(out)])
    assert run_r2_review.main() == 0
    for name in (
        "findings.json",
        "integration_recommendation.json",
        "adversarial_matrix_pass1.json",
        "adversarial_matrix_pass2.json",
        "metrics.json",
        "v11_review_durability_microstructure_status.json",
    ):
        assert (out / name).is_file(), name
    findings = json.loads((out / "findings.json").read_text(encoding="utf-8"))
    assert findings["integration_recommendation"]["critical_count"] >= 3
    assert findings["raw_campaign_evidence_modified"] is False
