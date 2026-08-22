"""Pinned P2 Zeabur CLI: direct deployment_id from UploadZipToService prepare URL."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.ci.p2_migration_bootstrap import evaluate_create_command_pass
from tools.ci.p2_migration_deployment_phase import (
    audit_deploy_output_deployment_id,
    evaluate_activation_deployment_discovery,
    evaluate_bootstrap_deployment_discovery,
    evaluate_exact_deployment_phase,
    evaluate_pinned_deploy_output,
)
from tools.ci.p2_migration_lifecycle_command import evaluate_activation_local_deploy

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "founder_approved_staging_postgres_p2_migration.yml"
PIN = ROOT / "deploy" / "zeabur_p2_migration_cli" / "PINNED_UPSTREAM_COMMIT"
PATCH = ROOT / "deploy" / "zeabur_p2_migration_cli" / "patches" / "001-deploy-emit-deployment-id.patch"
STAGING_ENV = "69d559b6474db8a99d6dd6bf"
SERVICE_ID = "abcdef0123456789abcdef01"
PROJECT_ID = "bbbbbbbbbbbbbbbbbbbbbbbb"
BOOTSTRAP_ID = "6a89a69fa158dec40572a046"
ACTIVATION_ID = "6a89a6cd29f0931a12bfea72"

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

ACTIVATION_DEPLOY_JSON = json.dumps(
    {
        "status": "success",
        "service_id": SERVICE_ID,
        "project_id": PROJECT_ID,
        "environment_id": STAGING_ENV,
        "deployment_id": ACTIVATION_ID,
        "message": "Service deployed successfully",
    }
)


def test_upstream_patch_and_pin_present():
    pin = PIN.read_text(encoding="utf-8").strip()
    assert len(pin) == 40
    patch = PATCH.read_text(encoding="utf-8")
    assert "deployment_id" in patch
    assert "UploadZipToService" in patch
    assert "deploymentIDFromPrepareURL" in patch
    assert "P2_ZEABUR_UPLOAD_DEPLOYMENT_ID" in patch
    assert 'deployment == nil || deployment.ID == ""' in patch
    assert "upload returned empty deployment id" in patch
    assert 'fmt.Fprintf(os.Stderr, "P2_ZEABUR_UPLOAD_DEPLOYMENT_ID=%s\\n", deployment.ID)' in patch


def test_a_marker_only_no_json_passes():
    marker_only = (
        f"P2_ZEABUR_UPLOAD_DEPLOYMENT_ID={BOOTSTRAP_ID}\n"
        f"P2_ZEABUR_UPLOAD_SERVICE_ID={SERVICE_ID}\n"
        f"P2_ZEABUR_UPLOAD_ENVIRONMENT_ID={STAGING_ENV}\n"
    )
    result = evaluate_pinned_deploy_output(
        deploy_output=marker_only,
        deploy_exit=0,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
        expected_project_id=PROJECT_ID,
        phase="bootstrap",
    )
    assert result["ok"] is True
    assert result["deployment_id"] == BOOTSTRAP_ID
    assert result["P2_ZEABUR_DIRECT_UPLOAD_MARKER_PRESENT"] is True
    assert result["P2_ZEABUR_DEPLOYMENT_ID_DIRECT_FROM_UPLOAD"] is True
    assert result["P2_MIGRATION_DEPLOYMENT_LIST_AUTHORITY"] is False


def test_b_json_deployment_id_only_compatibility_pass():
    result = evaluate_pinned_deploy_output(
        deploy_output=PINNED_DEPLOY_JSON,
        deploy_exit=0,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
        expected_project_id=PROJECT_ID,
        phase="bootstrap",
    )
    assert result["ok"] is True
    assert result["deployment_id"] == BOOTSTRAP_ID
    assert result["P2_ZEABUR_DIRECT_UPLOAD_MARKER_PRESENT"] is False
    assert result["P2_ZEABUR_DEPLOYMENT_ID_DIRECT_FROM_UPLOAD"] is True


def test_c_marker_and_json_same_id_pass():
    output = (
        f"P2_ZEABUR_UPLOAD_DEPLOYMENT_ID={BOOTSTRAP_ID}\n"
        f"{PINNED_DEPLOY_JSON}\n"
    )
    result = evaluate_pinned_deploy_output(
        deploy_output=output,
        deploy_exit=0,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
        phase="bootstrap",
    )
    assert result["ok"] is True
    assert result["deployment_id"] == BOOTSTRAP_ID
    assert result["P2_ZEABUR_DIRECT_UPLOAD_MARKER_PRESENT"] is True


def test_d_marker_and_json_conflicting_ids_fail_closed():
    output = (
        f"P2_ZEABUR_UPLOAD_DEPLOYMENT_ID={BOOTSTRAP_ID}\n"
        f"{ACTIVATION_DEPLOY_JSON}\n"
    )
    result = evaluate_pinned_deploy_output(
        deploy_output=output,
        deploy_exit=0,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
        phase="bootstrap",
    )
    assert result["ok"] is False
    assert result["marker_json_conflict"] is True
    assert result["deployment_id"] == ""


def test_e_missing_marker_and_missing_json_fails():
    result = evaluate_pinned_deploy_output(
        deploy_output="\n",
        deploy_exit=0,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
        phase="bootstrap",
    )
    assert result["ok"] is False
    assert result["P2_ZEABUR_DIRECT_UPLOAD_MARKER_PRESENT"] is False
    assert result["P2_ZEABUR_DEPLOYMENT_ID_DIRECT_FROM_UPLOAD"] is False


def test_f_malformed_marker_fails_closed():
    result = evaluate_pinned_deploy_output(
        deploy_output="P2_ZEABUR_UPLOAD_DEPLOYMENT_ID=not-a-valid-oid\n",
        deploy_exit=0,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
        phase="bootstrap",
    )
    assert result["ok"] is False
    assert result["marker_malformed"] is True

    empty = evaluate_pinned_deploy_output(
        deploy_output=f"P2_ZEABUR_UPLOAD_DEPLOYMENT_ID=\n{PINNED_DEPLOY_JSON}\n",
        deploy_exit=0,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
        phase="bootstrap",
    )
    assert empty["ok"] is False
    assert empty["marker_malformed"] is True


def test_g_go_patch_fail_closed_on_nil_or_empty_deployment():
    patch = PATCH.read_text(encoding="utf-8")
    assert "deployment == nil || deployment.ID == \"\"" in patch
    assert "upload returned empty deployment id" in patch


def test_bootstrap_direct_id_from_pinned_deploy_json():
    result = evaluate_pinned_deploy_output(
        deploy_output=PINNED_DEPLOY_JSON,
        deploy_exit=0,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
        expected_project_id=PROJECT_ID,
        phase="bootstrap",
    )
    assert result["ok"] is True
    assert result["deployment_id"] == BOOTSTRAP_ID
    assert result["P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY"] is True
    assert result["P2_ZEABUR_DEPLOYMENT_ID_DIRECT_FROM_UPLOAD"] is True
    assert result["P2_MIGRATION_DEPLOYMENT_LIST_AUTHORITY"] is False


def test_activation_direct_id_differs_from_bootstrap():
    result = evaluate_pinned_deploy_output(
        deploy_output=ACTIVATION_DEPLOY_JSON,
        deploy_exit=0,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
        expected_project_id=PROJECT_ID,
        phase="activation",
        bootstrap_deployment_id=BOOTSTRAP_ID,
    )
    assert result["ok"] is True
    assert result["deployment_id"] == ACTIVATION_ID
    assert result["distinct_from_bootstrap"] is True


def test_same_service_and_environment_required():
    bad_env = evaluate_pinned_deploy_output(
        deploy_output=json.dumps(
            {
                "status": "success",
                "service_id": SERVICE_ID,
                "project_id": PROJECT_ID,
                "environment_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
                "deployment_id": ACTIVATION_ID,
            }
        ),
        deploy_exit=0,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
        phase="activation",
        bootstrap_deployment_id=BOOTSTRAP_ID,
    )
    assert bad_env["ok"] is False

    bad_service = evaluate_pinned_deploy_output(
        deploy_output=json.dumps(
            {
                "status": "success",
                "service_id": "cccccccccccccccccccccccc",
                "project_id": PROJECT_ID,
                "environment_id": STAGING_ENV,
                "deployment_id": ACTIVATION_ID,
            }
        ),
        deploy_exit=0,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
        phase="activation",
        bootstrap_deployment_id=BOOTSTRAP_ID,
    )
    assert bad_service["ok"] is False


def test_missing_deployment_id_fails_closed():
    missing = evaluate_pinned_deploy_output(
        deploy_output=json.dumps(
            {
                "status": "success",
                "service_id": SERVICE_ID,
                "project_id": PROJECT_ID,
                "environment_id": STAGING_ENV,
                "message": "Service deployed successfully",
            }
        ),
        deploy_exit=0,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
        phase="bootstrap",
    )
    assert missing["ok"] is False
    assert missing["P2_ZEABUR_DEPLOYMENT_ID_DIRECT_FROM_UPLOAD"] is False


def test_activation_same_id_as_bootstrap_fails():
    same = evaluate_pinned_deploy_output(
        deploy_output=PINNED_DEPLOY_JSON,
        deploy_exit=0,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
        phase="activation",
        bootstrap_deployment_id=BOOTSTRAP_ID,
    )
    assert same["ok"] is False


def test_exact_phase_uses_deployment_get_not_list():
    get_payload = json.dumps({"_id": ACTIVATION_ID, "status": "RUNNING"})
    phase = evaluate_exact_deployment_phase(
        target_deployment_id=ACTIVATION_ID,
        deployment_get_raw=get_payload,
        deployment_list_raw='{"deployments":[]}',
        phase="activation",
    )
    assert phase["ready"] is True
    assert phase["exact_status"] == "RUNNING"


def test_deployment_list_empty_does_not_block_when_get_authority():
    get_payload = json.dumps({"deployment_id": ACTIVATION_ID, "status": "BUILDING"})
    phase = evaluate_exact_deployment_phase(
        target_deployment_id=ACTIVATION_ID,
        deployment_get_raw=get_payload,
        deployment_list_raw='{"deployments":[]}',
        phase="activation",
    )
    assert phase["exact_status"] == "BUILDING"
    assert phase["ready"] is False
    assert phase["wait"] is True


def test_list_discovery_marked_not_authority():
    bootstrap = evaluate_bootstrap_deployment_discovery(deployment_list_raw='{"deployments":[]}')
    assert bootstrap["P2_MIGRATION_DEPLOYMENT_LIST_AUTHORITY"] is False
    activation = evaluate_activation_deployment_discovery(
        baseline_deployment_ids=frozenset({BOOTSTRAP_ID}),
        deployment_list_raw='{"deployments":[]}',
    )
    assert activation["P2_MIGRATION_DEPLOYMENT_LIST_AUTHORITY"] is False


def test_unpinned_audit_has_no_deploy_id_authority():
    audit = audit_deploy_output_deployment_id(
        json.dumps({"status": "success", "service_id": SERVICE_ID}),
        pinned_cli=False,
    )
    assert audit["P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY"] is False


def test_create_pass_with_deployment_id_in_pinned_json():
    command = evaluate_create_command_pass(
        create_exit=0,
        service_id=SERVICE_ID,
        create_output=PINNED_DEPLOY_JSON,
    )
    assert command["ok"] is True


def test_activation_local_deploy_pass_without_list_authority():
    result = evaluate_activation_local_deploy(
        exit_code=0,
        output=ACTIVATION_DEPLOY_JSON,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
    )
    assert result["ok"] is True
    assert result["P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY"] is True


def test_pinned_cli_build_uses_upstream_cmd_main_go():
    script = (ROOT / "deploy" / "zeabur_p2_migration_cli" / "build_p2_zeabur_cli.sh").read_text(
        encoding="utf-8"
    )
    assert 'go build -o "${OUT_BIN}" ./cmd/main.go' in script
    assert "./cmd/zeabur" not in script
    assert "test -f cmd/main.go" in script
    assert "P2_ZEABUR_UPLOAD_DEPLOYMENT_ID" in script
    assert "P2_PINNED_CLI_DIRECT_MARKER_BINARY_PROOF=true" in script


def test_workflow_uses_pinned_cli_and_direct_ids():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "build_p2_zeabur_cli.sh" in source
    assert "P2_PINNED_ZEABUR_CLI_IMPLEMENTED=true" in source
    assert "P2_PINNED_CLI_DIRECT_MARKER_BINARY_PROOF=true" in source
    assert "P2_ZEABUR_DEPLOYMENT_ID_DIRECT_FROM_UPLOAD=true" in source
    assert "P2_MIGRATION_DEPLOYMENT_LIST_AUTHORITY=false" in source
    assert "--discover-bootstrap" not in source
    assert "--discover-activation" not in source
    assert "Discover activation deployment ID from deployment list" not in source
    assert "deployment get --deployment-id" in source
    assert "evaluate-pinned-deploy" in source
    assert "npm i -g zeabur@latest" not in source


def test_zero_exchange_writes():
    marker_only = f"P2_ZEABUR_UPLOAD_DEPLOYMENT_ID={BOOTSTRAP_ID}\n"
    result = evaluate_pinned_deploy_output(
        deploy_output=marker_only,
        deploy_exit=0,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
        phase="bootstrap",
    )
    assert result["ok"] is True
    assert result["exchange_write_call_count"] == 0
    assert result["create_order_calls"] == 0
