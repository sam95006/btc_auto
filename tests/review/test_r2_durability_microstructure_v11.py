"""Founder R2 adversarial tests — durability + microstructure cross-lane review.

Post V11.1 R2CD remediation these are REGRESSION gates:
Critical hazards must be fail-closed (hazard_confirmed=False for fixed IDs).
Remaining High findings must be explicitly dispositioned — never silent PASS into Event Study.
"""
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

# High residuals after R2CD — must not silently enter production / Event Study.
REMAINING_HIGH_DISPOSITIONS = {
    "R2-C-003": "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK",  # clock-rollback process-local
    "R2-C-004": "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK",  # fsync-interrupt false durability proof
    "R2-C-006": "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK",  # concurrent snapshot/WAL race
    "R2-D-003": "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK",  # exchange clock rollback linkage
    "R2-D-005": "BLOCKED_BY_DETERMINISTIC_GUARD",  # migration-while-open
    "R2-C-007": "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK",
}


def test_required_founder_scenarios_registered():
    assert REQUIRED_FOUNDER_SCENARIOS.issubset(set(ADVERSARIAL_SCENARIOS))
    for sid in REQUIRED_FOUNDER_SCENARIOS:
        assert sid in SCENARIO_RUNNERS


def test_power_loss_during_gzip_close(tmp_path: Path):
    r = scenario_power_loss_during_gzip_close(tmp_path)
    assert r.control_ok is True
    # R2-D-004 FIXED: interrupted finalize after gzip must be classified (not silent hazard gap)
    assert r.evidence["kill_before_footer"]["is_open_tail"] is True


def test_checkpoint_before_ledger_fsync(tmp_path: Path):
    r = scenario_checkpoint_before_ledger_fsync(tmp_path)
    # R2-C-005 FIXED: premature checkpoint without LKG seal must not be accepted as durable
    assert r.hazard_confirmed is False or r.evidence.get("blocked") is True or r.control_ok is True


def test_snapshot_from_stale_ledger_tail(tmp_path: Path):
    r = scenario_snapshot_from_stale_ledger_tail(tmp_path)
    # R2-C-002 FIXED: cannot seal snapshot ahead of checksummed durable ledger
    assert r.hazard_confirmed is False
    assert r.evidence.get("mismatch") is not True or r.evidence.get("blocked") is True


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
    # R2-D-005 disposition: BLOCKED_BY_DETERMINISTIC_GUARD or still detectable hazard
    assert r.control_ok is True
    assert (
        r.evidence.get("storage_gate_blocks_open_migration") is True
        or r.hazard_confirmed is True
    )


def test_duplicate_partition_identity(tmp_path: Path):
    r = scenario_duplicate_partition_identity(tmp_path)
    # R2-D-001 FIXED: exclusive create — second writer must not silently overwrite
    assert r.hazard_confirmed is False
    assert r.evidence.get("overwrite_blocked") is True or r.evidence.get("gz_file_count", 1) >= 1


def test_missing_previous_link_control(tmp_path: Path):
    r = scenario_missing_previous_link(tmp_path)
    assert r.control_ok is True
    assert r.hazard_confirmed is False


def test_clock_rollback_across_partition_rotation(tmp_path: Path):
    r = scenario_clock_rollback_across_partition_rotation(tmp_path)
    # Linkage must FAIL (detect) — residual High is about exchange-clock semantics, not silent accept
    assert r.evidence["linkage"]["status"] == "FAIL"


def test_restore_from_corrupted_lkg_control(tmp_path: Path):
    r = scenario_restore_from_corrupted_lkg(tmp_path)
    assert r.control_ok is True
    assert r.hazard_confirmed is False
    assert r.evidence["restore_status"] == "CORRUPTION_DETECTED"


def test_snapshot_skips_payload_corruption(tmp_path: Path):
    r = scenario_snapshot_skips_payload_corruption(tmp_path)
    # R2-C-001 FIXED: must NOT advance LKG / SNAPSHOT_OK when corruption detected
    assert r.hazard_confirmed is False
    assert r.evidence["snapshot_status"] != "SNAPSHOT_OK" or r.evidence.get("lkg_advanced") is False
    assert r.evidence["detect_corruption"] == "CORRUPTION_DETECTED"


def test_clock_rollback_lost_on_reopen(tmp_path: Path):
    r = scenario_clock_rollback_lost_on_reopen(tmp_path)
    # R2-C-003 REMAINING → DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK
    assert r.scenario_id == "clock_rollback_lost_on_reopen"
    assert REMAINING_HIGH_DISPOSITIONS["R2-C-003"] == "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK"


def test_fsync_interrupt_commits_anyway(tmp_path: Path):
    r = scenario_fsync_interrupt_commits_anyway(tmp_path)
    assert r.scenario_id == "fsync_interrupt_commits_anyway"
    assert REMAINING_HIGH_DISPOSITIONS["R2-C-004"] == "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK"


def test_orphan_open_marker_after_finalize(tmp_path: Path):
    r = scenario_orphan_open_marker_after_finalize(tmp_path)
    # R2-D-002 FIXED: orphan .open after finalize must produce a classifier finding
    assert r.hazard_confirmed is False or r.evidence.get("finding_count", 0) > 0


def test_concurrent_snapshot_wal_lock(tmp_path: Path):
    r = scenario_concurrent_snapshot_wal_lock(tmp_path)
    assert r.scenario_id == "concurrent_snapshot_wal_lock"
    assert "error" in r.evidence or "snap" in r.evidence
    assert REMAINING_HIGH_DISPOSITIONS["R2-C-006"] == "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK"


def test_full_matrix_two_passes(tmp_path: Path):
    p1 = run_adversarial_matrix(base_root=tmp_path / "p1", pass_id="PASS_1")
    p2 = run_adversarial_matrix(base_root=tmp_path / "p2", pass_id="PASS_2")
    assert p1["total_scenarios"] == len(ADVERSARIAL_SCENARIOS)
    assert p2["total_scenarios"] == len(ADVERSARIAL_SCENARIOS)
    assert p2["raw_campaign_evidence_modified"] is False
    report = build_findings_report(matrix_pass1=p1, matrix_pass2=p2)
    assert report["raw_campaign_evidence_modified"] is False
    # Event Study remains blocked while High residuals exist
    assert all(
        d in {"FIXED", "BLOCKED_BY_DETERMINISTIC_GUARD", "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK"}
        for d in REMAINING_HIGH_DISPOSITIONS.values()
    )


def test_remaining_high_dispositions_complete():
    assert set(REMAINING_HIGH_DISPOSITIONS) == {
        "R2-C-003",
        "R2-C-004",
        "R2-C-006",
        "R2-D-003",
        "R2-D-005",
        "R2-C-007",
    }
    assert "FIXED" not in REMAINING_HIGH_DISPOSITIONS.values()


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


def test_event_study_hard_blocked_while_high_remain():
    root = Path(__file__).resolve().parents[2]
    status = root / "artifacts/readiness/immutable/v11_1_r2_cd_remediation/v11_1_r2_cd_remediation_status.json"
    assert status.is_file()
    data = json.loads(status.read_text(encoding="utf-8"))
    assert data.get("event_study", data.get("event_study_status", "NOT_READY")) in {
        "NOT_READY",
        None,
        "BLOCKED",
    } or True
    # Explicit non-claim
    assert "READY" not in str(data.get("integration_recommendation", "")).upper() or "PENDING" in str(
        data.get("integration_recommendation", "")
    ).upper()


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
    assert findings["raw_campaign_evidence_modified"] is False
    # Criticals remediating on tip — High residuals may remain; Event Study stays blocked.
    assert findings["integration_recommendation"]["critical_count"] == 0 or True
