"""V10 Security & DR Red Team — fail-closed adversarial proofs."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)

from backend.nexus_autonomy.security_dr_redteam_v10 import (  # noqa: E402
    OWNED_PATHS,
    PASS_RECOMMENDATION,
    evaluate_security_dr_redteam,
    run_security_dr_redteam,
    write_immutable_artifacts,
)
from backend.nexus_autonomy.security_dr_scenarios_v10 import (  # noqa: E402
    SCENARIO_IDS,
    DRFailClosedError,
    load_checkpoint_fail_closed,
    reject_unsafe_deserialize,
    run_all_scenarios,
    scenario_checkpoint_corruption,
    scenario_concurrent_lifecycle,
    scenario_credential_boundary,
    scenario_demo_mainnet_confusion,
    scenario_duplicate_intent_recovery,
    scenario_filesystem_corruption,
    scenario_network_egress,
    scenario_path_traversal,
    scenario_power_loss,
    scenario_stale_restore,
    scenario_symlink_escape,
    scenario_unsafe_deserialization,
    simulate_power_loss_mid_write,
    write_checkpoint_atomic,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def workdir(tmp_path: Path) -> Path:
    return tmp_path / "dr_work"


def test_all_required_scenarios_listed():
    required = {
        "power_loss",
        "filesystem_corruption",
        "checkpoint_corruption",
        "concurrent_lifecycle",
        "path_traversal",
        "unsafe_deserialization",
        "credential_boundary",
        "network_egress",
        "demo_mainnet_confusion",
        "symlink_escape",
        "stale_restore",
        "duplicate_intent_recovery",
    }
    assert set(SCENARIO_IDS) == required
    assert len(SCENARIO_IDS) == 12


def test_power_loss_fail_closed(workdir: Path):
    r = scenario_power_loss(workdir)
    assert r.passed and r.fail_closed


def test_filesystem_corruption_fail_closed(workdir: Path):
    assert scenario_filesystem_corruption(workdir).passed


def test_checkpoint_corruption_fail_closed(workdir: Path):
    assert scenario_checkpoint_corruption(workdir).passed


def test_concurrent_lifecycle_fail_closed(workdir: Path):
    assert scenario_concurrent_lifecycle(workdir).passed


def test_path_traversal_fail_closed(workdir: Path):
    assert scenario_path_traversal(workdir).passed


def test_unsafe_deserialization_fail_closed(workdir: Path):
    assert scenario_unsafe_deserialization(workdir).passed
    with pytest.raises(DRFailClosedError):
        reject_unsafe_deserialize(b"\x80\x04", format_hint="pickle")


def test_credential_boundary_fail_closed(workdir: Path):
    assert scenario_credential_boundary(workdir).passed


def test_network_egress_fail_closed(workdir: Path):
    assert scenario_network_egress(workdir).passed


def test_demo_mainnet_confusion_fail_closed(workdir: Path):
    assert scenario_demo_mainnet_confusion(workdir).passed


def test_symlink_escape_fail_closed(workdir: Path):
    assert scenario_symlink_escape(workdir).passed


def test_stale_restore_fail_closed(workdir: Path):
    assert scenario_stale_restore(workdir).passed


def test_duplicate_intent_recovery_fail_closed(workdir: Path):
    assert scenario_duplicate_intent_recovery(workdir).passed


def test_run_all_scenarios_pass(workdir: Path):
    results = run_all_scenarios(workdir)
    assert len(results) == 12
    failed = [r.scenario_id for r in results if not r.passed]
    assert failed == [], failed


def test_evaluate_counters_zero(workdir: Path):
    status = evaluate_security_dr_redteam(root=ROOT, workdir=workdir)
    assert status["exchange_write_attempt_count"] == 0
    assert status["secret_leak_count"] == 0
    assert status["mainnet_client_created_count"] == 0
    assert status["demo_order_count"] == 0
    assert status["recommendation"] == PASS_RECOMMENDATION
    assert status["passed"] is True
    assert status["critical_findings"] == []


def test_immutable_artifacts_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Point immutable dir under tmp by evaluating with root=tmp that has structure
    # write into real owned artifact path via run with root=ROOT is fine for lane
    status = evaluate_security_dr_redteam(root=ROOT, workdir=tmp_path / "w")
    paths = write_immutable_artifacts(root=ROOT, status=status)
    assert paths["status"].is_file()
    loaded = json.loads(paths["status"].read_text(encoding="utf-8"))
    assert loaded["exchange_write_attempt_count"] == 0
    assert loaded["secret_leak_count"] == 0
    assert loaded["mainnet_client_created_count"] == 0
    assert loaded["recommendation"] == PASS_RECOMMENDATION
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert summary["critical_findings"] == []


def test_run_security_dr_redteam_end_to_end():
    status = run_security_dr_redteam(write_artifact=True, root=ROOT)
    assert status["passed"] is True
    assert status["scenario_pass_count"] == 12
    art = (
        ROOT
        / "artifacts"
        / "readiness"
        / "immutable"
        / "v10_security_dr_redteam"
        / "security_dr_redteam_status.json"
    )
    assert art.is_file()


def test_owned_paths_declared():
    assert any("security_dr_redteam_v10.py" in p for p in OWNED_PATHS)
    assert any("v10_security_dr_redteam" in p for p in OWNED_PATHS)


def test_incomplete_checkpoint_helper(workdir: Path):
    ckpt = workdir / "c.json"
    simulate_power_loss_mid_write(ckpt, {"generation": 1, "state": "X"})
    with pytest.raises(DRFailClosedError, match="incomplete_checkpoint"):
        load_checkpoint_fail_closed(ckpt)
    write_checkpoint_atomic(ckpt, {"generation": 9, "state": "OK"})
    data = load_checkpoint_fail_closed(ckpt)
    assert data["generation"] == 9
