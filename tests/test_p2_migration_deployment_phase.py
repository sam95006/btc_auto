"""P2 migration exact deployment-ID phase gates (bootstrap → activation sequencing)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.ci.p2_migration_bootstrap import extract_deployment_id_from_output
from tools.ci.p2_migration_deployment_phase import (
    build_log_progress_hash,
    can_start_activation_deploy,
    evaluate_exact_deployment_phase,
    find_deployment_by_id,
    gate_exit_code,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "founder_approved_staging_postgres_p2_migration.yml"
BOOTSTRAP_ID = "6a89a69fa158dec40572a046"
ACTIVATION_ID = "6a89a6cd29f0931a12bfea72"
CANCELED_BOOTSTRAP = "aaaaaaaaaaaaaaaaaaaaaaaa"


def _list_payload(*deployments: tuple[str, str]) -> str:
    items = [{"deployment_id": did, "status": status} for did, status in deployments]
    return json.dumps({"deployments": items})


def test_a_activation_blocked_while_bootstrap_building():
    bootstrap = evaluate_exact_deployment_phase(
        target_deployment_id=BOOTSTRAP_ID,
        deployment_list_raw=_list_payload((BOOTSTRAP_ID, "BUILDING")),
        phase="bootstrap",
    )
    gate = can_start_activation_deploy(bootstrap_phase=bootstrap)
    assert gate["blocked"] is True
    assert gate["P2_MIGRATION_ACTIVATION_BEFORE_BOOTSTRAP_READY_BLOCKED"] is True
    assert gate["ok"] is False


def test_b_bootstrap_running_allows_activation():
    bootstrap = evaluate_exact_deployment_phase(
        target_deployment_id=BOOTSTRAP_ID,
        deployment_list_raw=_list_payload((BOOTSTRAP_ID, "RUNNING")),
        phase="bootstrap",
    )
    assert bootstrap["ready"] is True
    assert bootstrap.get("P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_READY") is True
    gate = can_start_activation_deploy(bootstrap_phase=bootstrap)
    assert gate["ok"] is True
    assert gate["blocked"] is False


def test_c_old_canceled_deployment_does_not_contaminate_activation_status():
    # Activation target BUILDING; list also has old CANCELED bootstrap — authority is exact ID only.
    activation = evaluate_exact_deployment_phase(
        target_deployment_id=ACTIVATION_ID,
        deployment_list_raw=_list_payload(
            (CANCELED_BOOTSTRAP, "CANCELED"),
            (ACTIVATION_ID, "BUILDING"),
        ),
        phase="activation",
        bootstrap_deployment_id=CANCELED_BOOTSTRAP,
        activation_started=True,
    )
    assert activation["exact_status"] == "BUILDING"
    assert activation["ready"] is False
    assert activation["wait"] is True
    assert activation.get("P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_SUPERSEDED") is False

    record_list = _list_payload((CANCELED_BOOTSTRAP, "CANCELED"))
    obj = find_deployment_by_id(json.loads(record_list), ACTIVATION_ID)
    assert obj is None


def test_d_exact_activation_deployment_id_selected():
    raw = json.dumps({"deployment_id": ACTIVATION_ID, "status": "RUNNING"})
    assert extract_deployment_id_from_output(raw) == ACTIVATION_ID
    activation = evaluate_exact_deployment_phase(
        target_deployment_id=ACTIVATION_ID,
        deployment_list_raw=_list_payload((ACTIVATION_ID, "RUNNING")),
        phase="activation",
    )
    assert activation["target_deployment_id"] == ACTIVATION_ID
    assert activation["ready"] is True
    assert activation.get("P2_MIGRATION_ACTIVATION_DEPLOYMENT_READY") is True


def test_e_building_never_promoted_to_pass():
    for status in ("BUILDING", "PENDING", "DEPLOYING", "UNKNOWN"):
        result = evaluate_exact_deployment_phase(
            target_deployment_id=ACTIVATION_ID,
            deployment_list_raw=_list_payload((ACTIVATION_ID, status)),
            phase="activation",
        )
        assert result["ready"] is False
        assert result.get("P2_MIGRATION_ACTIVATION_DEPLOYMENT_READY") is not True


def test_f_stalled_build_reported_not_bypassed():
    log = "layer 1/5\n" * 50
    h = build_log_progress_hash(log)
    first = evaluate_exact_deployment_phase(
        target_deployment_id=ACTIVATION_ID,
        deployment_list_raw=_list_payload((ACTIVATION_ID, "BUILDING")),
        build_log_raw=log,
        phase="activation",
        prior_build_hash="",
        stall_count=0,
    )
    assert first["P2_MIGRATION_BUILD_STALLED"] is False
    second = evaluate_exact_deployment_phase(
        target_deployment_id=ACTIVATION_ID,
        deployment_list_raw=_list_payload((ACTIVATION_ID, "BUILDING")),
        build_log_raw=log,
        phase="activation",
        prior_build_hash=h,
        stall_count=first["stall_count"],
    )
    third = evaluate_exact_deployment_phase(
        target_deployment_id=ACTIVATION_ID,
        deployment_list_raw=_list_payload((ACTIVATION_ID, "BUILDING")),
        build_log_raw=log,
        phase="activation",
        prior_build_hash=h,
        stall_count=second["stall_count"],
    )
    fourth = evaluate_exact_deployment_phase(
        target_deployment_id=ACTIVATION_ID,
        deployment_list_raw=_list_payload((ACTIVATION_ID, "BUILDING")),
        build_log_raw=log,
        phase="activation",
        prior_build_hash=h,
        stall_count=third["stall_count"],
    )
    assert fourth["P2_MIGRATION_BUILD_STALLED"] is True
    assert fourth["hard_fail"] is True
    assert gate_exit_code(fourth) == 1


def test_g_bootstrap_superseded_when_canceled_after_early_activation():
    result = evaluate_exact_deployment_phase(
        target_deployment_id=BOOTSTRAP_ID,
        deployment_list_raw=_list_payload((BOOTSTRAP_ID, "CANCELED")),
        phase="bootstrap",
        bootstrap_deployment_id=BOOTSTRAP_ID,
        activation_started=True,
    )
    assert result["P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_SUPERSEDED"] is True
    assert result["hard_fail"] is True


def test_h_migration_cannot_start_before_activation_readiness_in_workflow():
    source = WORKFLOW.read_text(encoding="utf-8")
    act_ready_idx = source.index("Wait for exact activation deployment ready")
    op_idx = source.index("Operational service-exec readiness")
    migration_idx = source.index("Apply and verify only migration 0007 through atomic same-exec")
    assert act_ready_idx < op_idx < migration_idx
    assert "Wait for bootstrap deployment ready before runtime variables" in source
    bootstrap_idx = source.index("Wait for bootstrap deployment ready before runtime variables")
    vars_idx = source.index("Inject disarmed runtime variables after bootstrap deployment ready")
    assert bootstrap_idx < vars_idx


def test_i_zero_exchange_writes_on_phase_surfaces():
    result = evaluate_exact_deployment_phase(
        target_deployment_id=BOOTSTRAP_ID,
        deployment_list_raw=_list_payload((BOOTSTRAP_ID, "RUNNING")),
        phase="bootstrap",
    )
    gate = can_start_activation_deploy(bootstrap_phase=result)
    assert result["exchange_write_call_count"] == 0
    assert gate["exchange_write_call_count"] == 0
    assert result["create_order_calls"] == 0


def test_j_workflow_captures_bootstrap_and_activation_deployment_ids():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "bootstrap_deployment_id=" in source
    assert "P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_ID=" in source
    assert "activation_deployment_id=" in source
    assert "P2_MIGRATION_ACTIVATION_DEPLOYMENT_ID=" in source
    assert "p2_migration_deployment_phase" in source
    assert "BOOTSTRAP_DEPLOYMENT_READY_GATE_IMPLEMENTED=true" in source
    assert "--target-deployment-id" in source


def test_k_deploy_record_exact_id_isolates_canceled_bootstrap():
    from tools.ci.p2_migration_lifecycle_command import evaluate_deployment_record_present

    only_canceled = evaluate_deployment_record_present(
        deployment_list_raw=_list_payload((CANCELED_BOOTSTRAP, "CANCELED")),
        target_deployment_id=ACTIVATION_ID,
    )
    assert only_canceled["ok"] is False
    assert only_canceled["P2_MIGRATION_EXACT_DEPLOYMENT_ID_AUTHORITY"] is True

    with_activation = evaluate_deployment_record_present(
        deployment_list_raw=_list_payload(
            (CANCELED_BOOTSTRAP, "CANCELED"),
            (ACTIVATION_ID, "RUNNING"),
        ),
        target_deployment_id=ACTIVATION_ID,
    )
    assert with_activation["ok"] is True


def test_l_build_log_progress_hash_changes_reset_stall():
    log_a = "step-a\n" * 20
    log_b = "step-b\n" * 20
    ha = build_log_progress_hash(log_a)
    hb = build_log_progress_hash(log_b)
    assert ha != hb
    stalled = evaluate_exact_deployment_phase(
        target_deployment_id=ACTIVATION_ID,
        deployment_list_raw=_list_payload((ACTIVATION_ID, "BUILDING")),
        build_log_raw=log_b,
        phase="activation",
        prior_build_hash=ha,
        stall_count=2,
    )
    assert stalled["stall_count"] == 0


def test_m_missing_deployment_id_raises():
    with pytest.raises(ValueError, match="deployment_id_missing"):
        evaluate_exact_deployment_phase(
            target_deployment_id="",
            phase="bootstrap",
        )
