"""Tests for V12-D Disaster Recovery Control."""
from __future__ import annotations

import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["DEMO"] = "false"

from backend.nexus_recovery.dr_control_v12.constants import PROOF_IDS, V11_1_INVARIANT_IDS
from backend.nexus_recovery.dr_control_v12.control import DisasterRecoveryControlV12
from backend.nexus_recovery.dr_control_v12.proofs import (
    PROOF_RUNNERS,
    proof_ambiguous_state_blocking,
    proof_checkpoint_restore,
    proof_cold_restart,
    proof_kill_switch_after_recovery,
    proof_ledger_tail_reconciliation,
    proof_lkg_restore,
    proof_storage_migration_recovery,
    proof_warm_restart,
    run_proof_matrix,
)
from backend.nexus_runtime.durability_v2.constants import SNAPSHOT_OK


def test_all_proof_runners_registered():
    assert set(PROOF_IDS) == set(PROOF_RUNNERS)
    assert len(PROOF_IDS) == 8
    assert len(V11_1_INVARIANT_IDS) == 3


def test_cold_restart(tmp_path: Path):
    r = proof_cold_restart(tmp_path)
    assert r.passed, r.detail


def test_warm_restart(tmp_path: Path):
    r = proof_warm_restart(tmp_path)
    assert r.passed, r.detail


def test_lkg_restore(tmp_path: Path):
    r = proof_lkg_restore(tmp_path)
    assert r.passed, r.detail


def test_checkpoint_restore(tmp_path: Path):
    r = proof_checkpoint_restore(tmp_path)
    assert r.passed, r.detail


def test_ledger_tail_reconciliation(tmp_path: Path):
    r = proof_ledger_tail_reconciliation(tmp_path)
    assert r.passed, r.detail
    assert r.detail["reconcile"]["position_source"] == "checksummed_main_file"


def test_ambiguous_state_blocking(tmp_path: Path):
    r = proof_ambiguous_state_blocking(tmp_path)
    assert r.passed, r.detail


def test_kill_switch_after_recovery(tmp_path: Path):
    r = proof_kill_switch_after_recovery(tmp_path)
    assert r.passed, r.detail


def test_storage_migration_recovery(tmp_path: Path):
    r = proof_storage_migration_recovery(tmp_path)
    assert r.passed, r.detail


def test_full_matrix_pass(tmp_path: Path):
    report = run_proof_matrix(tmp_path / "matrix")
    assert report["overall_status"] == "NEXUS_V12_DISASTER_RECOVERY_CONTROL_PASS", report
    assert report["counters"]["proofs_passed"] == 8
    assert report["counters"]["invariants_passed"] == 3
    assert report["counters"]["exchange_write_attempt_count"] == 0
    assert report["counters"]["demo_order_count"] == 0
    assert report["counters"]["silent_recovery_guess_count"] == 0
    assert report["counters"]["PR27_merged"] is False


def test_kill_switch_blocks_seed(tmp_path: Path):
    c = DisasterRecoveryControlV12(tmp_path / "ks")
    assert c.seed_events(2).get("status") == "PASS"
    c.kill_switch(reason="unit")
    blocked = c.seed_events(1)
    assert blocked["status"] == "KILL_SWITCH_BLOCKS"


def test_seed_creates_sealed_checkpoint(tmp_path: Path):
    c = DisasterRecoveryControlV12(tmp_path / "seal")
    out = c.seed_events(3)
    assert out["status"] == "PASS"
    assert out["snapshot"]["status"] == SNAPSHOT_OK
    seal = c.durability.validate_checkpoint_seal()
    assert seal["status"] == "PASS"
