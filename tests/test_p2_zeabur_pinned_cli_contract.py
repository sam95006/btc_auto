"""Pinned P2 Zeabur CLI exit propagation + runtime operational authority contract."""
from __future__ import annotations

import json
from pathlib import Path

from tools.ci.p2_migration_bootstrap import evaluate_create_command_pass
from tools.ci.p2_migration_deployment_phase import (
    audit_deploy_output_deployment_id,
    evaluate_pinned_deploy_output,
)
from tools.ci.p2_migration_rollout_readiness import (
    ACTIVATION_READINESS_PASS_MARKER,
    BOOTSTRAP_READINESS_PASS_MARKER,
    classify_readiness_probe_output,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "founder_approved_staging_postgres_p2_migration.yml"
PIN = ROOT / "deploy" / "zeabur_p2_migration_cli" / "PINNED_UPSTREAM_COMMIT"
PATCH = ROOT / "deploy" / "zeabur_p2_migration_cli" / "patches" / "001-deploy-emit-deployment-id.patch"
BUILD = ROOT / "deploy" / "zeabur_p2_migration_cli" / "build_p2_zeabur_cli.sh"
STAGING_ENV = "69d559b6474db8a99d6dd6bf"


def _patch_result_for_file(filename: str) -> str:
    patch = PATCH.read_text(encoding="utf-8")
    in_file = False
    result: list[str] = []
    for line in patch.splitlines():
        if line.startswith("diff --git"):
            in_file = filename in line
            continue
        if not in_file:
            continue
        if line.startswith(("+++", "---", "@@", "diff ")):
            continue
        if line.startswith("-"):
            continue
        if line.startswith("+"):
            result.append(line[1:])
        elif line.startswith(" "):
            result.append(line[1:])
    return "\n".join(result)


def _deploy_go_patch_result() -> str:
    return _patch_result_for_file("internal/cmd/deploy/deploy.go")


SERVICE_ID = "abcdef0123456789abcdef01"
PROJECT_ID = "bbbbbbbbbbbbbbbbbbbbbbbb"
BOOTSTRAP_ID = "6a89a69fa158dec40572a046"
SHA = "af02f1ab7d312d1c4faeeba412a519bfd070ae23"

PINNED_DEPLOY_JSON = json.dumps(
    {
        "status": "success",
        "service_id": SERVICE_ID,
        "project_id": PROJECT_ID,
        "environment_id": STAGING_ENV,
        "deployment_id": BOOTSTRAP_ID,
        "message": "Service deployed successfully",
    }
)


def _valid_bootstrap_probe(*, sha: str = SHA) -> str:
    return (
        f"expected_sha={sha}\n"
        f"baked_sha={sha}\n"
        f"source_sha={sha}\n"
        f"expected_sha_prefix={sha[:12]}\n"
        f"baked_sha_prefix={sha[:12]}\n"
        f"source_sha_prefix={sha[:12]}\n"
        "helper_present=true\n"
        "safety_flags_ok=true\n"
        "P2_MIGRATION_CURRENT_IMAGE_PROBE_PASS=true\n"
        f"{BOOTSTRAP_READINESS_PASS_MARKER}\n"
    )


def _valid_activation_probe(*, sha: str = SHA) -> str:
    return _valid_bootstrap_probe(sha=sha) + "dsn_present=true\n" + f"{ACTIVATION_READINESS_PASS_MARKER}\n"


def test_upstream_patch_propagates_execute_error_exit():
    pin = PIN.read_text(encoding="utf-8").strip()
    assert len(pin) == 40
    patch = PATCH.read_text(encoding="utf-8")
    added = _deploy_go_patch_result()
    assert "cmd/main.go" in patch
    assert "os.Exit(1)" in patch
    assert "internal/cmd/deploy/deploy.go" in patch
    assert "UploadZipToService" in added
    assert "GetEnvironment" not in added.split("if opts.serviceID != \"\" && opts.environmentID != \"\"")[1].split("UploadZipToService")[0]


def test_a_create_path_skips_get_environment_when_env_explicit():
    added = _deploy_go_patch_result()
    assert "explicitEnvironment(opts.environmentID, projectID)" in added
    assert "P2_DEPLOY_GRAPHQL_ENV_LOOKUP_SKIPPED" in added
    assert "CreateEmptyService" in added
    create_block = added.split('emitDeployDiagnostic("P2_DEPLOY_STAGE", "create_service")', 1)[1]
    assert "GetEnvironment" not in create_block.split("UploadZipToService")[0]


def test_b_activation_path_skips_get_service_and_get_environment():
    added = _deploy_go_patch_result()
    assert "if opts.serviceID != \"\" && opts.environmentID != \"\"" in added
    assert "P2_DEPLOY_GRAPHQL_SERVICE_LOOKUP_SKIPPED" in added
    assert "explicitService(opts.serviceID, projectID)" in added
    activation_block = added.split("if opts.serviceID != \"\" && opts.environmentID != \"\"")[1].split("} else if opts.serviceID")[0]
    assert "GetService" not in activation_block
    assert "GetEnvironment" not in activation_block


def test_c_upload_zip_to_service_still_called():
    added = _deploy_go_patch_result()
    assert "UploadZipToService(context.Background(), projectID, service.ID, environment.ID, bytes)" in added
    assert "P2_DEPLOY_UPLOAD_STARTED" in added
    assert "P2_DEPLOY_UPLOAD_PASS" in added


def test_d_upload_error_emits_fail_and_propagates():
    added = _deploy_go_patch_result()
    assert "P2_DEPLOY_UPLOAD_FAIL" in added
    assert "return err" in added.split("UploadZipToService", 1)[1]


def test_e_missing_explicit_environment_fails_closed():
    added = _deploy_go_patch_result()
    assert "environment-id required when project-id is explicit" in added
    assert "environment-id required when service-id is explicit" in added


def test_f_no_first_environment_fallback_when_project_explicit():
    added = _deploy_go_patch_result()
    project_branch = added.split('if opts.projectID != ""', 1)[1].split("} else if opts.serviceID")[0]
    assert "ListEnvironments" not in project_branch


def test_deploy_stage_diagnostics_present():
    patch = PATCH.read_text(encoding="utf-8")
    for key in (
        "P2_DEPLOY_PACK_ZIP_PASS",
        "P2_DEPLOY_CREATE_SERVICE_PASS",
        "P2_DEPLOY_SERVICE_ID_EXPLICIT",
        "P2_DEPLOY_ENVIRONMENT_ID_EXPLICIT",
        "P2_DEPLOY_GRAPHQL_ENV_LOOKUP_SKIPPED",
        "P2_DEPLOY_GRAPHQL_SERVICE_LOOKUP_SKIPPED",
        "P2_DEPLOY_UPLOAD_STARTED",
        "P2_DEPLOY_UPLOAD_PASS",
        "P2_DEPLOY_UPLOAD_FAIL",
        "P2_DEPLOY_STAGE",
    ):
        assert key in patch


def test_build_script_uses_cmd_main_go_and_exit_propagation():
    script = BUILD.read_text(encoding="utf-8")
    assert 'go build -o "${OUT_BIN}" ./cmd/main.go' in script
    assert "grep -q 'os.Exit(1)'" in script
    assert "grep -q 'P2_DEPLOY_GRAPHQL_ENV_LOOKUP_SKIPPED'" in script
    assert "EXPLICIT_ID_DIRECT_UPLOAD_IMPLEMENTED=true" in script
    assert "P2_ZEABUR_CLI_EXIT_PROPAGATION_FIXED=true" in script
    assert "OPERATIONAL_RUNTIME_SHA_AUTHORITY=true" in script
    assert "P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY=false" in script


def test_deployment_id_audit_only_never_control_authority():
    audit = audit_deploy_output_deployment_id(PINNED_DEPLOY_JSON, pinned_cli=True)
    assert audit["P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY"] is False
    assert audit["DEPLOYMENT_ID_AUDIT_ONLY"] is True
    assert audit["deploy_output_deployment_id_present"] is True

    parsed = evaluate_pinned_deploy_output(
        deploy_output=PINNED_DEPLOY_JSON,
        deploy_exit=0,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
        phase="bootstrap",
    )
    assert parsed["deployment_id"] == BOOTSTRAP_ID
    assert parsed["P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY"] is False
    assert parsed["DEPLOYMENT_ID_AUDIT_ONLY"] is True
    assert parsed["OPERATIONAL_RUNTIME_SHA_AUTHORITY"] is True


def test_missing_deployment_id_does_not_block_audit_parse():
    missing = evaluate_pinned_deploy_output(
        deploy_output='{"status":"success","service_id":"%s"}' % SERVICE_ID,
        deploy_exit=0,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
        phase="bootstrap",
    )
    assert missing["P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY"] is False
    assert missing["P2_ZEABUR_DEPLOYMENT_ID_DIRECT_FROM_UPLOAD"] is False


def test_bootstrap_runtime_three_pass_classifier():
    op = classify_readiness_probe_output(_valid_bootstrap_probe(), expected_sha=SHA, phase="bootstrap")
    assert op["ready"] is True
    assert op["OPERATIONAL_RUNTIME_SHA_AUTHORITY"] is True
    assert op["P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY"] is False


def test_activation_runtime_requires_dsn_presence():
    without_dsn = classify_readiness_probe_output(_valid_bootstrap_probe(), expected_sha=SHA, phase="activation")
    assert without_dsn["ready"] is False
    assert without_dsn["dsn_present"] is False

    with_dsn = classify_readiness_probe_output(_valid_activation_probe(), expected_sha=SHA, phase="activation")
    assert with_dsn["ready"] is True
    assert with_dsn["dsn_present"] is True


def test_create_pass_without_deployment_id():
    command = evaluate_create_command_pass(
        create_exit=0,
        service_id=SERVICE_ID,
        create_output='{"service_id":"%s","environment_id":"%s"}' % (SERVICE_ID, STAGING_ENV),
    )
    assert command["ok"] is True


def test_workflow_no_longer_uses_pinned_cli_build():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "build_p2_zeabur_cli.sh" not in source
    assert "setup-go" not in source
    assert "Operational runtime readiness before migration" in source
    assert "OPERATIONAL_RUNTIME_SHA_AUTHORITY=true" in source
    assert "P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY=false" in source
    assert "DEPLOYMENT_ID_AUDIT_ONLY=true" in source
    assert "THREE_CONSECUTIVE_RUNTIME_PROOFS_REQUIRED=true" in source
    assert "ACTIVATION_THREE_PASS_RUNTIME_PROOF=true" in source
    assert "ACTIVATION_DSN_PRESENCE_PROOF=true" in source
    assert "vars.ZEABUR_P2_MIGRATION_CONTROL_SERVICE_ID" in source
    assert "Create run-scoped migration service" not in source
    ready_idx = source.index("Operational runtime readiness before migration")
    migrate_idx = source.index("Apply and verify only migration 0007 through atomic same-exec")
    assert ready_idx < migrate_idx


def test_zero_exchange_writes():
    parsed = evaluate_pinned_deploy_output(
        deploy_output=PINNED_DEPLOY_JSON,
        deploy_exit=0,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
        phase="bootstrap",
    )
    assert parsed["exchange_write_call_count"] == 0
    assert parsed["create_order_calls"] == 0
