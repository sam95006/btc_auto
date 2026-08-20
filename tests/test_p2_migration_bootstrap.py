"""P2 migration single-deploy bootstrap: migration context first, no repo-root deploy."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.ci.p2_migration_bootstrap import (
    build_migration_context,
    extract_service_id_from_create_output,
    plan_single_create_deploy,
    sanitize_bootstrap_failure_diagnostics,
    validate_migration_context,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "founder_approved_staging_postgres_p2_migration.yml"
SHA = "b2971e8a278655ff298236d80b95bb20faa844e6"
ENSURE = (ROOT / "tools" / "ci" / "ensure_p2_migration_zeabur_service.py").read_text(encoding="utf-8")


def test_graphql_unavailable_path_does_not_plan_repo_root_deployment(tmp_path: Path):
    ctx = build_migration_context(repo_root=ROOT, destination=tmp_path / "ctx", github_sha=SHA)
    plan = plan_single_create_deploy(
        context_dir=ctx,
        service_name="nexus-p2m7-100-1",
        project_id="aaaaaaaaaaaaaaaaaaaaaaaa",
        repo_root=ROOT,
    )
    assert plan["cwd"] == str(ctx.resolve())
    assert plan["cwd"] != str(ROOT.resolve())
    assert "--create" in plan["argv"]
    assert plan["uses_create_empty_cli"] is False
    assert plan["P2_MIGRATION_BOOTSTRAP_DEPLOY_COUNT"] == 1
    assert plan["second_deploy_planned"] is False
    assert "Intentionally never call zeabur_svc._create_empty()" in ENSURE
    assert "Never calls shared _create_empty_cli()" in ENSURE
    assert "plan_single_create_deploy" in ENSURE
    assert "_create_with_migration_context" in ENSURE
    # Must not invoke shared empty-create helpers.
    assert "zeabur_svc._create_empty_cli(" not in ENSURE
    assert "zeabur_svc._create_empty()" not in ENSURE.replace(
        "Intentionally never call zeabur_svc._create_empty() or _create_empty_cli().",
        "",
    )


def test_migration_context_built_with_baked_commits_before_create(tmp_path: Path):
    ctx = build_migration_context(repo_root=ROOT, destination=tmp_path / "mig", github_sha=SHA)
    meta = validate_migration_context(ctx, expected_sha=SHA)
    assert meta["ok"] is True
    assert (ctx / "DEPLOYMENT_COMMIT").read_text(encoding="ascii").strip() == SHA
    assert (ctx / "SOURCE_COMMIT").read_text(encoding="ascii").strip() == SHA
    assert (ctx / "tools" / "ci" / "p2_staging_migration_0007.py").is_file()
    assert "NEXUS_POSTGRES_URL" not in (ctx / "Dockerfile").read_text(encoding="utf-8")
    assert meta["dsn_baked_in_image"] is False
    assert meta["exchange_write_call_count"] == 0


def test_cli_create_plan_is_exactly_one_deployment_from_context(tmp_path: Path):
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "DEPLOYMENT_COMMIT").write_text(SHA + "\n", encoding="ascii")
    (ctx / "SOURCE_COMMIT").write_text(SHA + "\n", encoding="ascii")
    helper = ctx / "tools" / "ci"
    helper.mkdir(parents=True)
    helper.joinpath("p2_staging_migration_0007.py").write_text("x=1\n", encoding="utf-8")
    (ctx / "Dockerfile").write_text("FROM python:3.11-slim-bookworm\n", encoding="utf-8")
    plan = plan_single_create_deploy(
        context_dir=ctx,
        service_name="nexus-p2m7-101-1",
        project_id="bbbbbbbbbbbbbbbbbbbbbbbb",
        repo_root=ROOT,
    )
    assert plan["argv"][:3] == ["zeabur", "deploy", "--create"]
    assert plan["P2_MIGRATION_SINGLE_DEPLOY_BOOTSTRAP"] is True
    assert plan["P2_MIGRATION_BOOTSTRAP_DEPLOY_COUNT"] == 1
    with pytest.raises(ValueError, match="migration_context_must_not_be_repo_root"):
        plan_single_create_deploy(
            context_dir=ROOT,
            service_name="nexus-p2m7-101-1",
            project_id="bbbbbbbbbbbbbbbbbbbbbbbb",
            repo_root=ROOT,
        )


def test_workflow_builds_context_before_create_and_has_no_second_deploy():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "Build migration deployment context before service create" in source
    assert "Create run-scoped migration service with single migration-context deploy" in source
    assert "Inject disarmed runtime variables after single bootstrap deploy" in source
    assert "P2_MIGRATION_CONTEXT_BUILT_BEFORE_SERVICE_CREATE=true" in source
    assert "P2_MIGRATION_SINGLE_DEPLOY_BOOTSTRAP=true" in source
    assert "P2_MIGRATION_BOOTSTRAP_DEPLOY_COUNT=1" in source
    assert "P2_MIGRATION_SECOND_DEPLOY=false" in source
    assert "P2_MIGRATION_CONTEXT_DIR" in source
    build_idx = source.index("Build migration deployment context before service create")
    create_idx = source.index("Create run-scoped migration service with single migration-context deploy")
    vars_idx = source.index("Inject disarmed runtime variables after single bootstrap deploy")
    assert build_idx < create_idx < vars_idx
    # No second deploy-to-existing-service after create for the bootstrap path.
    assert "zeabur deploy --project-id \"$ZEABUR_PROJECT_ID\" --service-id \"$SERVICE_ID\"" not in source
    assert "Configure disarmed migration boundary and deploy fresh migration image" not in source


def test_extract_service_id_and_sanitized_diagnostics():
    raw = 'noise {"service_id":"abcdef0123456789abcdef01"} tail'
    assert extract_service_id_from_create_output(raw) == "abcdef0123456789abcdef01"
    diag = sanitize_bootstrap_failure_diagnostics(
        create_deploy_exit=1,
        create_deploy_output="postgresql://user:secret@host/db " + ("x" * 80),
        service_id="abcdef0123456789abcdef01",
        service_name="nexus-p2m7-7-1",
        readiness_attempts=12,
        not_running_count=12,
        current_image_positive_proof_count=0,
    )
    assert diag["service_id_prefix"] == "abcdef"
    assert diag["not_running_count"] == 12
    assert "secret" not in diag["create_deploy_output_tail"]
    assert "postgresql://***" in diag["create_deploy_output_tail"]
    assert diag["exchange_write_call_count"] == 0
