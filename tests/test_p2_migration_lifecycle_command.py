"""P2 migration lifecycle: redeploy semantic guards + deployment-record gate."""
from __future__ import annotations

from pathlib import Path

from tools.ci.p2_migration_lifecycle_command import (
    evaluate_activation_local_deploy,
    evaluate_deployment_record_present,
    evaluate_lifecycle_command_pass,
)
from tools.ci.p2_migration_bootstrap import verify_context_source_identity
from tools.ci.p2_migration_rollout_readiness import (
    CURRENT_IMAGE_PROBE_PASS_MARKER,
    OPERATIONAL_READINESS_PASS_MARKER,
    classify_readiness_probe_output,
    wait_for_current_image_streak,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "founder_approved_staging_postgres_p2_migration.yml"
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


def test_a_restart_exit0_with_semantic_error_is_not_pass():
    result = evaluate_lifecycle_command_pass(
        operation="restart",
        exit_code=0,
        output=(
            "restart service failed:\n"
            "Message: Internal Server Error\n"
            "code: INTERNAL_SERVER_ERROR\n"
            "Path: [restartService]\n"
        ),
    )
    assert result["ok"] is False
    assert result["P2_MIGRATION_POST_VAR_RESTART"] is False
    assert result["P2_MIGRATION_POST_VAR_RESTART_COMMAND_PASS"] is False
    assert result["P2_MIGRATION_POST_VAR_RESTART_COUNT"] == 0
    assert result["cli_semantic_error"]


def test_b_redeploy_exit0_with_internal_server_error_is_not_pass():
    result = evaluate_lifecycle_command_pass(
        operation="redeploy",
        exit_code=0,
        output="redeploy service failed\ncode: INTERNAL_SERVER_ERROR\n",
    )
    assert result["ok"] is False
    assert result["P2_MIGRATION_POST_VAR_REDEPLOY"] is False
    assert result["P2_MIGRATION_POST_VAR_REDEPLOY_COMMAND_PASS"] is False


def test_c_redeploy_clean_success_pass():
    result = evaluate_lifecycle_command_pass(
        operation="redeploy",
        exit_code=0,
        output='{"ok":true,"message":"redeploy requested"}\n',
    )
    assert result["ok"] is True
    assert result["P2_MIGRATION_POST_VAR_REDEPLOY"] is True
    assert result["P2_MIGRATION_POST_VAR_REDEPLOY_COMMAND_PASS"] is True
    assert result["P2_MIGRATION_POST_VAR_REDEPLOY_COUNT"] == 1
    assert result["exchange_write_call_count"] == 0


def test_d_no_deployment_object_fails_before_service_exec():
    absent = evaluate_deployment_record_present(
        deployment_get_raw="",
        deployment_list_raw='{"skipped":"deployment_list_optional"}',
    )
    assert absent["ok"] is False
    assert absent["P2_MIGRATION_DEPLOYMENT_RECORD_PRESENT"] is False
    source = WORKFLOW.read_text(encoding="utf-8")
    record_idx = source.index("Require deployment record before service-exec")
    op_idx = source.index("Operational service-exec readiness")
    assert record_idx < op_idx
    assert "BLOCKER_deployment_record_absent_before_service_exec" in source
    assert "--deployment-get-exit" in source
    assert "--deployment-list-exit" in source
    assert "DEPLOYMENT_GET_EXIT=" in source
    assert "DEPLOYMENT_LIST_EXIT=" in source


def test_record_a_status_403_error_envelope_is_not_deployment():
    result = evaluate_deployment_record_present(
        deployment_get_raw='{"status":403,"error_code":1010,"error_name":"browser_signature_banned"}',
        deployment_get_exit=0,
        deployment_list_exit=0,
    )
    assert result["ok"] is False
    assert result["P2_MIGRATION_DEPLOYMENT_RECORD_PRESENT"] is False
    assert result["cli_semantic_error"]


def test_record_b_status_only_unknown_is_not_deployment():
    result = evaluate_deployment_record_present(
        deployment_get_raw='{"Status":"UNKNOWN"}',
        deployment_get_exit=0,
        deployment_list_exit=0,
    )
    assert result["ok"] is False
    assert result["deployment_id_count"] == 0


def test_record_c_valid_id_with_unknown_status_is_present():
    result = evaluate_deployment_record_present(
        deployment_get_raw='{"_id":"abcdef0123456789abcdef01","Status":"UNKNOWN"}',
        deployment_get_exit=0,
        deployment_list_exit=1,
    )
    assert result["ok"] is True
    assert result["P2_MIGRATION_DEPLOYMENT_RECORD_PRESENT"] is True


def test_record_d_list_with_valid_deployment_id_is_present():
    result = evaluate_deployment_record_present(
        deployment_get_raw="",
        deployment_list_raw='[{"deployment_id":"fedcba9876543210fedcba98","status":"DEPLOYING"}]',
        deployment_get_exit=1,
        deployment_list_exit=0,
    )
    assert result["ok"] is True
    assert result["deployment_id_prefix"] == "fedcba"


def test_record_e_nonzero_exits_without_valid_id_is_false():
    result = evaluate_deployment_record_present(
        deployment_get_raw="failed to get deployment",
        deployment_list_raw="",
        deployment_get_exit=1,
        deployment_list_exit=1,
    )
    assert result["ok"] is False


def test_record_f_exit0_with_semantic_error_text_is_false():
    result = evaluate_deployment_record_present(
        deployment_get_raw="INTERNAL_SERVER_ERROR\naccess_denied\n",
        deployment_list_raw="",
        deployment_get_exit=0,
        deployment_list_exit=0,
    )
    assert result["ok"] is False
    assert result["cli_semantic_error"]


def test_e_deployment_exists_service_not_running_allows_bounded_operational_wait():
    present = evaluate_deployment_record_present(
        deployment_get_raw='{"_id":"abcdef0123456789abcdef01","status":"UNKNOWN"}',
        deployment_list_raw="[]",
    )
    assert present["ok"] is True
    assert present["P2_MIGRATION_DEPLOYMENT_RECORD_PRESENT"] is True
    op = classify_readiness_probe_output(
        "ERROR execute command failed\ncode=NOT_RUNNING_SERVICE\nThis service is not in the running state\n",
        expected_sha=SHA,
    )
    assert op["not_running_yet"] is True
    assert op["hard_fail"] is False
    assert op["ready"] is False


def test_f_deployment_exists_and_three_operational_passes():
    present = evaluate_deployment_record_present(
        deployment_get_raw='{"deployment_id":"abcdef0123456789abcdef01","Status":"DEPLOYING"}',
    )
    assert present["ok"] is True

    def probe(_a: int) -> dict:
        return {"stdout": _valid(), "exit_code": 0, "expected_sha": SHA}

    result = wait_for_current_image_streak(
        probe=probe, max_attempts=12, consecutive_needed=3, sleep=lambda _s: None
    )
    assert result["converged"] is True
    assert result["streak"] == 3


def test_i_zero_exchange_writes_on_lifecycle_surfaces():
    restart = evaluate_lifecycle_command_pass(operation="restart", exit_code=0, output="ok")
    redeploy = evaluate_lifecycle_command_pass(operation="redeploy", exit_code=0, output="ok")
    record = evaluate_deployment_record_present(deployment_get_raw='{"_id":"abcdef0123456789abcdef01"}')
    assert restart["exchange_write_call_count"] == 0
    assert redeploy["create_order_calls"] == 0
    assert record["exchange_write_call_count"] == 0


def test_workflow_uses_local_deploy_not_service_redeploy_after_vars():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "Activation local deploy to same service after runtime variables" in source
    assert "zeabur deploy" in source
    assert '--project-id "$ZEABUR_PROJECT_ID"' in source
    assert '--service-id "$SERVICE_ID"' in source
    assert '--environment-id "$ZEABUR_ENV_ID"' in source
    assert "P2_MIGRATION_POST_VAR_LOCAL_DEPLOY=true" in source
    assert "P2_MIGRATION_POST_VAR_LOCAL_DEPLOY_COMMAND_PASS=true" in source
    assert "P2_MIGRATION_POST_VAR_SOURCE_IDENTITY_PASS" in source
    assert "p2_migration_lifecycle_command" in source
    assert "zeabur service redeploy" not in source
    assert "Restart staging service once after runtime variables" not in source
    assert "P2_MIGRATION_POST_VAR_RESTART=true" not in source
    assert "P2_MIGRATION_POST_VAR_REDEPLOY=true" not in source
    vars_idx = source.index("Inject disarmed runtime variables after bootstrap deployment ready")
    act_idx = source.index("Activation local deploy to same service after runtime variables")
    act_ready_idx = source.index("Wait for exact activation deployment ready")
    meta_idx = source.index("Metadata diagnostic and explicit-negative veto")
    record_idx = source.index("Require deployment record before service-exec")
    op_idx = source.index("Operational service-exec readiness")
    assert vars_idx < act_idx < act_ready_idx < meta_idx < record_idx < op_idx
    activation_block = source[act_idx:meta_idx]
    cmd = activation_block[activation_block.index("--project-id \"$ZEABUR_PROJECT_ID\"") :]
    cmd = cmd.split(")", 1)[0]
    assert "--create" not in cmd
    assert "--service-id \"$SERVICE_ID\"" in cmd
    assert "--environment-id \"$ZEABUR_ENV_ID\"" in cmd
    assert "p2_migration_deployment_phase" in source
    assert "--target-deployment-id" in source
    assert "P2_MIGRATION_EXACT_DEPLOYMENT_ID_AUTHORITY=true" in source or "--target-deployment-id" in source


def test_activation_f_returned_service_id_mismatch_fail_closed():
    result = evaluate_activation_local_deploy(
        exit_code=0,
        output='{"service_id":"aaaaaaaaaaaaaaaaaaaaaaaa","environment_id":"69d559b6474db8a99d6dd6bf"}',
        expected_service_id="bbbbbbbbbbbbbbbbbbbbbbbb",
        expected_environment_id="69d559b6474db8a99d6dd6bf",
    )
    assert result["ok"] is False
    assert result["P2_MIGRATION_POST_VAR_SERVICE_MATCH"] is False


def test_activation_g_returned_env_id_mismatch_fail_closed():
    result = evaluate_activation_local_deploy(
        exit_code=0,
        output='{"service_id":"bbbbbbbbbbbbbbbbbbbbbbbb","environment_id":"aaaaaaaaaaaaaaaaaaaaaaaa"}',
        expected_service_id="bbbbbbbbbbbbbbbbbbbbbbbb",
        expected_environment_id="69d559b6474db8a99d6dd6bf",
    )
    assert result["ok"] is False
    assert result["P2_MIGRATION_POST_VAR_ENV_MATCH"] is False


def test_activation_h_wrong_source_sha_fails_before_upload(tmp_path: Path):
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "DEPLOYMENT_COMMIT").write_text("1111111111111111111111111111111111111111\n", encoding="ascii")
    (ctx / "SOURCE_COMMIT").write_text("1111111111111111111111111111111111111111\n", encoding="ascii")
    result = verify_context_source_identity(context_dir=ctx, expected_sha=SHA)
    assert result["ok"] is False
    assert result["P2_MIGRATION_POST_VAR_SOURCE_IDENTITY_PASS"] is False


def test_activation_clean_pass_with_matching_ids_and_deployment_id():
    result = evaluate_activation_local_deploy(
        exit_code=0,
        output=(
            '{"service_id":"bbbbbbbbbbbbbbbbbbbbbbbb","environment_id":"69d559b6474db8a99d6dd6bf",'
            '"deployment_id":"6a89a6cd29f0931a12bfea72"}'
        ),
        expected_service_id="bbbbbbbbbbbbbbbbbbbbbbbb",
        expected_environment_id="69d559b6474db8a99d6dd6bf",
    )
    assert result["ok"] is True
    assert result["returned_deployment_id"] == "6a89a6cd29f0931a12bfea72"
    assert result["P2_MIGRATION_ACTIVATION_DEPLOYMENT_ID"] == "6a89a6cd29f0931a12bfea72"
    assert result["P2_MIGRATION_POST_VAR_LOCAL_DEPLOY_COMMAND_PASS"] is True
    assert result["P2_MIGRATION_SECOND_SERVICE_CREATED"] is False
    assert result["exchange_write_call_count"] == 0
