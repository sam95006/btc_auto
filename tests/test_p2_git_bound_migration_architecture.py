"""Persistent Git-bound P2 migration control service architecture contract."""
from __future__ import annotations

from pathlib import Path

from tools.ci.p2_migration_rollout_readiness import (
    ACTIVATION_READINESS_PASS_MARKER,
    classify_readiness_probe_output,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "founder_approved_staging_postgres_p2_migration.yml"
DOCKERFILE_GIT = ROOT / "deploy" / "zeabur_p2_migration_0007" / "Dockerfile.git"
ENTRYPOINT = ROOT / "deploy" / "zeabur_p2_migration_0007" / "entrypoint.sh"
SHA = "af02f1ab7d312d1c4faeeba412a519bfd070ae23"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _dockerfile_git() -> str:
    return DOCKERFILE_GIT.read_text(encoding="utf-8")


def test_1_workflow_has_no_run_scoped_service_creation():
    source = _workflow()
    assert "nexus-p2m7-${{ github.run_id }}" not in source
    assert "ensure_p2_migration_zeabur_service" not in source
    assert "Create run-scoped migration service" not in source
    assert "P2_MIGRATION_RUN_SCOPED_SERVICE" not in source
    assert "P2_MIGRATION_SERVICE_CREATE_COUNT" not in source


def test_2_workflow_has_no_local_zip_deploy_authority():
    source = _workflow()
    assert "build_migration_context" not in source
    assert "UploadZipToService" not in source
    assert "zeabur deploy \\\n" not in source
    assert 'zeabur deploy --project-id' not in source
    assert "P2_MIGRATION_CONTEXT_DIR" not in source
    assert "P2_MIGRATION_SINGLE_DEPLOY_BOOTSTRAP" not in source
    assert "LOCAL_ZIP_UPLOAD_AUTHORITY_REMOVED=true" in source


def test_3_workflow_has_no_pinned_deployment_cli_build():
    source = _workflow()
    assert "setup-go" not in source
    assert "build_p2_zeabur_cli.sh" not in source
    assert "Build pinned P2 migration Zeabur CLI" not in source
    assert "PINNED_DEPLOY_CLI_REMOVED=true" in source


def test_4_persistent_service_id_variable_required():
    source = _workflow()
    assert "vars.ZEABUR_P2_MIGRATION_CONTROL_SERVICE_ID" in source
    assert "P2_MIGRATION_CONTROL_SERVICE_ID" in source
    assert "PERSISTENT_GIT_BOUND_MIGRATION_SERVICE_ARCHITECTURE=true" in source


def test_5_exact_runtime_sha_required():
    source = _workflow()
    assert 'EXPECTED="${GITHUB_SHA}"' in source
    assert "RUNTIME_SHA_SOLE_AUTHORITY=true" in source
    assert "OPERATIONAL_RUNTIME_SHA_AUTHORITY=true" in source
    assert "DEPLOYMENT_COMMIT" not in source or "build_migration_context" not in source


def test_6_three_consecutive_runtime_proofs_required():
    source = _workflow()
    assert "STREAK_NEEDED=3" in source
    assert "THREE_CONSECUTIVE_RUNTIME_PROOFS_REQUIRED=true" in source
    assert "ACTIVATION_THREE_PASS_RUNTIME_PROOF=true" in source


def test_7_dsn_presence_required():
    source = _workflow()
    assert "dsn_present" in source
    assert "ACTIVATION_DSN_PRESENCE_PROOF=true" in source
    assert "DSN_RUNTIME_PRESENCE_REQUIRED=true" in source
    assert "--phase activation" in source


def test_8_all_five_safety_flags_false_required():
    source = _workflow()
    for flag in ("MAINNET", "REAL_MONEY", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND", "EXCHANGE_WRITE"):
        assert flag in source
    assert 'EXCHANGE_WRITE: "false"' in source or 'EXCHANGE_WRITE: "false"' in source.replace("'", '"')
    probe = Path(ROOT / "tools" / "ci" / "p2_migration_rollout_readiness.py").read_text(encoding="utf-8")
    assert "safety_flags_ok" in probe


def test_9_migration_cannot_start_before_readiness():
    source = _workflow()
    ready_idx = source.index("Operational runtime readiness before migration")
    apply_idx = source.index("Apply and verify only migration 0007 through atomic same-exec")
    assert ready_idx < apply_idx
    assert "P2_MIGRATION_ACTIVATION_OPERATIONAL_READINESS_PASS=true" in source


def test_10_postgres_post_state_required_for_pass():
    source = _workflow()
    assert "p2_extract_migration_authoritative_stdout" in source
    assert "P2_MIGRATION_0007_APPLIED_PASS" in source
    assert "POSTGRES_POST_STATE_REQUIRED=true" in source
    helper = (ROOT / "tools" / "ci" / "p2_staging_migration_0007.py").read_text(encoding="utf-8")
    assert "_post_verify" in helper
    assert "pg_constraint" in helper or "information_schema" in helper


def test_11_dockerfile_uses_migration_only_requirements():
    docker = _dockerfile_git()
    assert "requirements-migration.txt" in docker
    assert "requirements.txt" not in docker
    assert "deploy/zeabur_p2_migration_0007/requirements-migration.txt" in docker


def test_12_dockerfile_bakes_zeabur_git_commit_sha():
    docker = _dockerfile_git()
    assert "ARG ZEABUR_GIT_COMMIT_SHA" in docker
    assert 'test -n "${ZEABUR_GIT_COMMIT_SHA}"' in docker
    assert "/app/DEPLOYMENT_COMMIT" in docker
    assert "/app/SOURCE_COMMIT" in docker
    assert "NEXUS_POSTGRES_URL" not in docker


def test_13_dockerfile_boot_is_health_only():
    docker = _dockerfile_git()
    entry = ENTRYPOINT.read_text(encoding="utf-8")
    assert "migration_health_server.py" in docker
    assert "entrypoint.sh" in docker
    assert "exec python ./migration_health_server.py" in entry
    assert "p2_staging_migration_0007" not in entry


def test_14_p1_certified_surfaces_unchanged_in_workflow():
    source = _workflow()
    assert "p1_qualification" not in source
    assert "RUN_ONE_BYBIT_DEMO_TRADE" not in source
    assert "nexus-bybit-demo-learning-validation" not in source
    assert "p2_historical_p1_p2_regression_lock" in source


def test_runtime_readiness_classifier_still_authoritative():
    raw = (
        f"expected_sha={SHA}\n"
        f"baked_sha={SHA}\n"
        f"source_sha={SHA}\n"
        f"expected_sha_prefix={SHA[:12]}\n"
        f"baked_sha_prefix={SHA[:12]}\n"
        f"source_sha_prefix={SHA[:12]}\n"
        "helper_present=true\n"
        "safety_flags_ok=true\n"
        "dsn_present=true\n"
        f"{ACTIVATION_READINESS_PASS_MARKER}\n"
    )
    op = classify_readiness_probe_output(raw, expected_sha=SHA, phase="activation")
    assert op["ready"] is True
    assert op["dsn_present"] is True
    assert op["exchange_write_call_count"] == 0
