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
    assert "cmd/main.go" in patch
    assert "os.Exit(1)" in patch
    assert "UploadZipToService" not in patch
    assert "P2_ZEABUR_UPLOAD_DEPLOYMENT_ID" not in patch


def test_build_script_uses_cmd_main_go_and_exit_propagation():
    script = BUILD.read_text(encoding="utf-8")
    assert 'go build -o "${OUT_BIN}" ./cmd/main.go' in script
    assert "grep -q 'os.Exit(1)'" in script
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


def test_workflow_uses_runtime_authority_not_deployment_id_control():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "build_p2_zeabur_cli.sh" in source
    assert "P2_ZEABUR_CLI_EXIT_PROPAGATION_FIXED=true" in source
    assert "Bootstrap operational readiness before runtime variables" in source
    assert "Activation operational readiness before migration" in source
    assert "OPERATIONAL_RUNTIME_SHA_AUTHORITY=true" in source
    assert "P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY=false" in source
    assert "DEPLOYMENT_ID_AUDIT_ONLY=true" in source
    assert "P2_MIGRATION_ORPHAN_CLEANUP_SERVICE_ID=" in source
    assert "BOOTSTRAP_THREE_PASS_RUNTIME_PROOF=true" in source
    assert "ACTIVATION_THREE_PASS_RUNTIME_PROOF=true" in source
    assert "ACTIVATION_DSN_PRESENCE_PROOF=true" in source
    assert "Wait for bootstrap deployment ready before runtime variables" not in source
    assert "Wait for exact activation deployment ready" not in source
    assert "Require deployment record before service-exec" not in source
    assert "Operational service-exec readiness" not in source
    assert "BLOCKER_bootstrap_deploy_missing_direct_deployment_id" not in source
    create_idx = source.index("Create run-scoped migration service with single migration-context deploy")
    bootstrap_idx = source.index("Bootstrap operational readiness before runtime variables")
    vars_idx = source.index("Inject disarmed runtime variables after bootstrap operational proof")
    act_idx = source.index("Activation local deploy to same service after runtime variables")
    act_ready_idx = source.index("Activation operational readiness before migration")
    migrate_idx = source.index("Apply and verify only migration 0007 through atomic same-exec")
    assert create_idx < bootstrap_idx < vars_idx < act_idx < act_ready_idx < migrate_idx


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
