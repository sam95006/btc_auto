"""End-to-end offline control-flow tests for P2 migration readiness model."""
from __future__ import annotations

from pathlib import Path

from tools.ci.p2_migration_deployment_diagnostics import classify_deployment_snapshot
from tools.ci.p2_migration_rollout_readiness import (
    CURRENT_IMAGE_PROBE_PASS_MARKER,
    OPERATIONAL_READINESS_PASS_MARKER,
    classify_readiness_probe_output,
    wait_for_current_image_streak,
)

WORKFLOW = Path(".github/workflows/founder_approved_staging_postgres_p2_migration.yml")
SHA = "af02f1ab7d312d1c4faeeba412a519bfd070ae23"


def _valid(*, sha: str = SHA) -> str:
    return (
        f"expected_sha={sha}\n"
        f"baked_sha={sha}\n"
        f"source_sha={sha}\n"
        f"expected_sha_prefix={sha[:12]}\n"
        f"baked_sha_prefix={sha[:12]}\n"
        f"source_sha_prefix={sha[:12]}\n"
        "helper_present=true\n"
        "safety_flags_ok=true\n"
        f"{CURRENT_IMAGE_PROBE_PASS_MARKER}\n"
        f"{OPERATIONAL_READINESS_PASS_MARKER}\n"
    )


def test_a_metadata_unknown_service_exec_not_running_waits():
    meta = classify_deployment_snapshot(
        deployment_get_raw="{}",
        service_get_raw='{"Status":"UNKNOWN"}',
        service_get_exit=0,
    )
    assert meta["proceed_to_operational_probe"] is True
    assert meta["service_exec_allowed"] is False
    op = classify_readiness_probe_output(
        "ERROR execute command failed\ncode=NOT_RUNNING_SERVICE\nThis service is not in the running state\n",
        expected_sha=SHA,
    )
    assert op["ready"] is False
    assert op["not_running_yet"] is True
    assert op["hard_fail"] is False


def test_b_metadata_unknown_valid_operational_pass():
    meta = classify_deployment_snapshot(service_get_raw='{"Status":"UNKNOWN"}', service_get_exit=0)
    assert meta["proceed_to_operational_probe"] is True
    op = classify_readiness_probe_output(_valid(), expected_sha=SHA)
    assert op["ready"] is True
    assert op["P2_MIGRATION_OPERATIONAL_READINESS_PASS"] == "true"


def test_c_wrong_sha_fail_closed():
    raw = (
        f"expected_sha={SHA}\n"
        "baked_sha=1111111111111111111111111111111111111111\n"
        "source_sha=1111111111111111111111111111111111111111\n"
        f"expected_sha_prefix={SHA[:12]}\n"
        "baked_sha_prefix=111111111111\n"
        "source_sha_prefix=111111111111\n"
        "helper_present=true\n"
        "safety_flags_ok=true\n"
        "P2_MIGRATION_OPERATIONAL_READINESS_PASS=false\n"
    )
    op = classify_readiness_probe_output(raw, expected_sha=SHA)
    assert op["ready"] is False
    assert op["hard_fail"] is True


def test_d_safety_flag_true_fail_closed():
    raw = (
        f"expected_sha={SHA}\n"
        f"baked_sha={SHA}\n"
        f"source_sha={SHA}\n"
        f"expected_sha_prefix={SHA[:12]}\n"
        f"baked_sha_prefix={SHA[:12]}\n"
        f"source_sha_prefix={SHA[:12]}\n"
        "helper_present=true\n"
        "safety_flags_ok=false\n"
        "safety_flag_bad=MAINNET\n"
        "P2_MIGRATION_OPERATIONAL_READINESS_PASS=false\n"
    )
    op = classify_readiness_probe_output(raw, expected_sha=SHA)
    assert op["hard_fail"] is True
    assert op["ready"] is False


def test_e_metadata_failed_blocks_even_if_exec_would_pass():
    meta = classify_deployment_snapshot(
        deployment_get_raw='{"status":"FAILED"}',
        service_get_raw='{"status":"RUNNING"}',
    )
    assert meta["metadata_veto"] is True
    assert meta["proceed_to_operational_probe"] is False
    # Operational proof alone is irrelevant when metadata vetoed upstream.
    op = classify_readiness_probe_output(_valid(), expected_sha=SHA)
    assert op["ready"] is True
    assert meta["proceed_to_operational_probe"] is False


def test_f_three_consecutive_operational_proofs():
    def probe(_a: int) -> dict:
        return {"stdout": _valid(), "exit_code": 0, "expected_sha": SHA}

    result = wait_for_current_image_streak(
        probe=probe, max_attempts=12, consecutive_needed=3, sleep=lambda _s: None
    )
    assert result["converged"] is True
    assert result["streak"] == 3
    assert [row.get("current_image_streak") for row in result["history"]] == [1, 2, 3]


def test_g_migration_cannot_start_before_operational_pass_in_workflow():
    source = WORKFLOW.read_text(encoding="utf-8")
    ready_idx = source.index("Operational runtime readiness before migration")
    apply_idx = source.index("Apply and verify only migration 0007 through atomic same-exec")
    assert ready_idx < apply_idx
    assert "P2_MIGRATION_ACTIVATION_OPERATIONAL_READINESS_PASS=true" in source
    assert "Metadata diagnostic audit-only" in source


def test_h_zero_exchange_writes_in_readiness_surfaces():
    meta = classify_deployment_snapshot(service_get_raw='{"Status":"UNKNOWN"}')
    op = classify_readiness_probe_output(_valid(), expected_sha=SHA)
    assert meta["exchange_write_call_count"] == 0
    assert meta["create_order_calls"] == 0
    assert op["exchange_write_call_count"] == 0
    assert op["create_order_calls"] == 0
