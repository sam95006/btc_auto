"""P2 migration single-deploy bootstrap: migration context first, explicit env targeting."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.ci.p2_migration_bootstrap import (
    assert_create_env_argv_match,
    audit_create_environment_output,
    build_migration_context,
    evaluate_create_command_pass,
    extract_service_id_from_create_output,
    plan_activation_local_deploy,
    plan_single_create_deploy,
    sanitize_bootstrap_failure_diagnostics,
    validate_migration_context,
    verify_context_source_identity,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "founder_approved_staging_postgres_p2_migration.yml"
SHA = "b2971e8a278655ff298236d80b95bb20faa844e6"
STAGING_ENV = "69d559b6474db8a99d6dd6bf"
ENSURE = (ROOT / "tools" / "ci" / "ensure_p2_migration_zeabur_service.py").read_text(encoding="utf-8")
READINESS = (ROOT / "tools" / "ci" / "p2_migration_rollout_readiness.py").read_text(encoding="utf-8")


def test_graphql_unavailable_path_does_not_plan_repo_root_deployment(tmp_path: Path):
    ctx = build_migration_context(repo_root=ROOT, destination=tmp_path / "ctx", github_sha=SHA)
    plan = plan_single_create_deploy(
        context_dir=ctx,
        service_name="nexus-p2m7-100-1",
        project_id="aaaaaaaaaaaaaaaaaaaaaaaa",
        environment_id=STAGING_ENV,
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
    assert (ctx / "requirements-migration.txt").is_file()
    assert "psycopg" in (ctx / "requirements-migration.txt").read_text(encoding="utf-8")
    assert not (ctx / "requirements.txt").exists()
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
        environment_id=STAGING_ENV,
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
            environment_id=STAGING_ENV,
            repo_root=ROOT,
        )


def test_a_plan_without_environment_id_raises():
    with pytest.raises(ValueError, match="environment_id_missing"):
        plan_single_create_deploy(
            context_dir="/tmp/ctx",
            service_name="nexus-p2m7-1-1",
            project_id="cccccccccccccccccccccccc",
            environment_id="",
        )
    with pytest.raises(TypeError):
        plan_single_create_deploy(  # type: ignore[call-arg]
            context_dir="/tmp/ctx",
            service_name="nexus-p2m7-1-1",
            project_id="cccccccccccccccccccccccc",
        )


def test_b_c_argv_contains_explicit_environment_id_no_implicit_fallback(tmp_path: Path):
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    plan = plan_single_create_deploy(
        context_dir=ctx,
        service_name="nexus-p2m7-102-1",
        project_id="dddddddddddddddddddddddd",
        environment_id=STAGING_ENV,
    )
    argv = plan["argv"]
    assert "--environment-id" in argv
    assert argv[argv.index("--environment-id") + 1] == STAGING_ENV
    assert plan["P2_MIGRATION_CREATE_ENV_EXPLICIT"] is True
    assert plan["implicit_first_environment_fallback"] is False
    # Must not omit environment-id (Zeabur would then pick environments[0]).
    assert argv == [
        "zeabur",
        "deploy",
        "--create",
        "--name",
        "nexus-p2m7-102-1",
        "--project-id",
        "dddddddddddddddddddddddd",
        "--environment-id",
        STAGING_ENV,
        "-i=false",
        "--json",
    ]


def test_d_e_create_output_env_audit_match_mismatch_not_returned():
    other = "aaaaaaaaaaaaaaaaaaaaaaaa"
    mismatch = audit_create_environment_output(
        create_output=(
            '{"service_id":"abcdef0123456789abcdef01",'
            f'"project_id":"bbbbbbbbbbbbbbbbbbbbbbbb","environment_id":"{other}"}}'
        ),
        expected_environment_id=STAGING_ENV,
    )
    assert mismatch["ok"] is False
    assert mismatch["blocks_create"] is True
    assert mismatch["P2_MIGRATION_CREATE_ENV_OUTPUT_STATUS"] == "MISMATCH"
    assert mismatch["P2_MIGRATION_CREATE_ENV_MATCH"] is False

    ok = audit_create_environment_output(
        create_output=(
            '{"service_id":"abcdef0123456789abcdef01",'
            f'"project_id":"bbbbbbbbbbbbbbbbbbbbbbbb","environment_id":"{STAGING_ENV}"}}'
        ),
        expected_environment_id=STAGING_ENV,
    )
    assert ok["ok"] is True
    assert ok["blocks_create"] is False
    assert ok["P2_MIGRATION_CREATE_ENV_OUTPUT_STATUS"] == "MATCH"
    assert ok["P2_MIGRATION_CREATE_ENV_MATCH"] is True
    assert ok["environment_id"] == STAGING_ENV
    assert ok["service_id"] == "abcdef0123456789abcdef01"
    assert ok["exchange_write_call_count"] == 0

    missing = audit_create_environment_output(
        create_output='{"service_id":"abcdef0123456789abcdef01"}',
        expected_environment_id=STAGING_ENV,
    )
    assert missing["ok"] is True
    assert missing["blocks_create"] is False
    assert missing["P2_MIGRATION_CREATE_ENV_OUTPUT_STATUS"] == "NOT_RETURNED"
    assert missing["P2_MIGRATION_CREATE_ENV_MATCH"] is False


def test_a_missing_returned_env_with_argv_match_and_create_pass():
    plan = plan_single_create_deploy(
        context_dir="/tmp/ctx-a",
        service_name="nexus-p2m7-200-1",
        project_id="ffffffffffffffffffffffff",
        environment_id=STAGING_ENV,
    )
    arg = assert_create_env_argv_match(plan["argv"], expected_environment_id=STAGING_ENV)
    assert arg["ok"] is True
    assert arg["P2_MIGRATION_CREATE_ENV_ARG_MATCH"] is True
    audit = audit_create_environment_output(
        create_output='{"service_id":"abcdef0123456789abcdef01"}',
        expected_environment_id=STAGING_ENV,
    )
    assert audit["P2_MIGRATION_CREATE_ENV_OUTPUT_STATUS"] == "NOT_RETURNED"
    assert audit["blocks_create"] is False
    command = evaluate_create_command_pass(
        create_exit=0,
        service_id="abcdef0123456789abcdef01",
        create_output='{"service_id":"abcdef0123456789abcdef01"}',
    )
    assert command["ok"] is True
    assert command["P2_MIGRATION_CREATE_COMMAND_PASS"] is True


def test_b_wrong_argv_env_fails_before_create():
    bad = [
        "zeabur",
        "deploy",
        "--create",
        "--name",
        "nexus-p2m7-201-1",
        "--project-id",
        "ffffffffffffffffffffffff",
        "--environment-id",
        "aaaaaaaaaaaaaaaaaaaaaaaa",
        "-i=false",
        "--json",
    ]
    arg = assert_create_env_argv_match(bad, expected_environment_id=STAGING_ENV)
    assert arg["ok"] is False
    assert arg["P2_MIGRATION_CREATE_ENV_ARG_MATCH"] is False
    missing_flag = assert_create_env_argv_match(
        ["zeabur", "deploy", "--create", "--name", "x", "--project-id", "y", "-i=false", "--json"],
        expected_environment_id=STAGING_ENV,
    )
    assert missing_flag["ok"] is False
    dup = assert_create_env_argv_match(
        [
            "zeabur",
            "deploy",
            "--create",
            "--environment-id",
            STAGING_ENV,
            "--environment-id",
            STAGING_ENV,
            "-i=false",
            "--json",
        ],
        expected_environment_id=STAGING_ENV,
    )
    assert dup["ok"] is False


def test_c_returned_env_differs_fail_closed():
    audit = audit_create_environment_output(
        create_output='{"service_id":"abcdef0123456789abcdef01","environment_id":"aaaaaaaaaaaaaaaaaaaaaaaa"}',
        expected_environment_id=STAGING_ENV,
    )
    assert audit["P2_MIGRATION_CREATE_ENV_OUTPUT_STATUS"] == "MISMATCH"
    assert audit["blocks_create"] is True
    assert audit["ok"] is False


def test_e_missing_returned_env_is_not_mismatch():
    audit = audit_create_environment_output(
        create_output='deploy ok service_id=abcdef0123456789abcdef01',
        expected_environment_id=STAGING_ENV,
    )
    assert audit["P2_MIGRATION_CREATE_ENV_OUTPUT_STATUS"] == "NOT_RETURNED"
    assert audit["P2_MIGRATION_CREATE_ENV_OUTPUT_STATUS"] != "MISMATCH"
    assert audit["blocks_create"] is False


def test_f_g_h_workflow_same_env_vars_and_activation_local_deploy():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "ZEABUR_ENV_ID: 69d559b6474db8a99d6dd6bf" in source
    assert "ZEABUR_ENV_ID: ${{ env.ZEABUR_ENV_ID }}" in source
    assert 'variable create --id "$SERVICE_ID" --env-id "$ZEABUR_ENV_ID"' in source
    assert 'variable update --id "$SERVICE_ID" --env-id "$ZEABUR_ENV_ID"' in source
    assert "Wait for bootstrap deployment ready before runtime variables" in source
    assert "Inject disarmed runtime variables after bootstrap deployment ready" in source
    assert "Activation local deploy to same service after runtime variables" in source
    assert "zeabur deploy" in source
    assert '--project-id "$ZEABUR_PROJECT_ID"' in source
    assert '--service-id "$SERVICE_ID"' in source
    assert '--environment-id "$ZEABUR_ENV_ID"' in source
    assert "P2_MIGRATION_POST_VAR_LOCAL_DEPLOY=true" in source
    assert "P2_MIGRATION_POST_VAR_LOCAL_DEPLOY_COMMAND_PASS=true" in source
    assert "P2_MIGRATION_POST_VAR_LOCAL_DEPLOY_COUNT=1" in source
    assert "P2_MIGRATION_TOTAL_LOCAL_DEPLOY_COUNT=2" in source
    assert "P2_MIGRATION_SECOND_SERVICE_CREATED=false" in source
    assert "zeabur service redeploy" not in source
    assert "zeabur service restart --id" not in source
    # Activation deploy must not use --create.
    act_idx = source.index("Activation local deploy to same service after runtime variables")
    meta_idx = source.index("Metadata diagnostic and explicit-negative veto")
    activation_block = source[act_idx:meta_idx]
    assert 'zeabur deploy \\\n              --project-id "$ZEABUR_PROJECT_ID"' in activation_block or (
        'zeabur deploy' in activation_block and '--project-id "$ZEABUR_PROJECT_ID"' in activation_block
    )
    cmd = activation_block[activation_block.index("--project-id \"$ZEABUR_PROJECT_ID\"") :]
    cmd = cmd.split(")", 1)[0]
    assert "--create" not in cmd
    assert "--service-id \"$SERVICE_ID\"" in cmd
    assert "--environment-id \"$ZEABUR_ENV_ID\"" in cmd
    vars_idx = source.index("Inject disarmed runtime variables after bootstrap deployment ready")
    bootstrap_wait_idx = source.index("Wait for bootstrap deployment ready before runtime variables")
    create_idx = source.index("Create run-scoped migration service with single migration-context deploy")
    assert create_idx < bootstrap_wait_idx < vars_idx < act_idx < meta_idx


def test_i_operational_readiness_unchanged_in_ensure_and_workflow():
    # Ensure does not rewrite readiness classifier.
    assert "classify_readiness_probe_output" not in ENSURE
    assert "wait_for_current_image_streak" not in ENSURE
    # Rollout readiness module markers remain the operational authority.
    assert "P2_MIGRATION_OPERATIONAL_READINESS_PASS" in READINESS
    assert "NOT_RUNNING_SERVICE" in READINESS
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "Operational service-exec readiness" in source
    assert "python -m tools.ci.p2_migration_rollout_readiness" in source


def test_j_zero_exchange_writes_in_plan_and_workflow():
    plan = plan_single_create_deploy(
        context_dir="/tmp/ctx-x",
        service_name="nexus-p2m7-103-1",
        project_id="eeeeeeeeeeeeeeeeeeeeeeee",
        environment_id=STAGING_ENV,
    )
    assert plan["exchange_write_call_count"] == 0
    assert plan["create_order_calls"] == 0
    source = WORKFLOW.read_text(encoding="utf-8")
    assert 'set_var EXCHANGE_WRITE false' in source
    assert "EXCHANGE_WRITE: \"false\"" in source or 'EXCHANGE_WRITE: "false"' in source


def test_workflow_builds_context_before_create_and_has_no_second_service():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "Build migration deployment context before service create" in source
    assert "Create run-scoped migration service with single migration-context deploy" in source
    assert "Inject disarmed runtime variables after bootstrap deployment ready" in source
    assert "P2_MIGRATION_CONTEXT_BUILT_BEFORE_SERVICE_CREATE=true" in source
    assert "P2_MIGRATION_SINGLE_DEPLOY_BOOTSTRAP=true" in source
    assert "P2_MIGRATION_BOOTSTRAP_DEPLOY_COUNT=1" in source
    assert "P2_MIGRATION_SERVICE_CREATE_COUNT=1" in source
    assert "P2_MIGRATION_TOTAL_LOCAL_DEPLOY_COUNT=2" in source
    assert "P2_MIGRATION_SECOND_SERVICE_CREATED=false" in source
    assert "P2_MIGRATION_CREATE_ENV_EXPLICIT=true" in source
    assert "P2_MIGRATION_CONTEXT_DIR" in source
    build_idx = source.index("Build migration deployment context before service create")
    create_idx = source.index("Create run-scoped migration service with single migration-context deploy")
    vars_idx = source.index("Inject disarmed runtime variables after bootstrap deployment ready")
    assert build_idx < create_idx < vars_idx
    # No second deploy-to-existing-service after create for the bootstrap path.
    assert "zeabur deploy --project-id \"$ZEABUR_PROJECT_ID\" --service-id \"$SERVICE_ID\"" not in source.split(
        "Activation local deploy to same service after runtime variables"
    )[0]
    assert "Configure disarmed migration boundary and deploy fresh migration image" not in source


def test_ensure_requires_zeabur_env_id_and_verifies_arg_not_output_authority():
    assert "ZEABUR_ENV_ID" in ENSURE
    assert "BLOCKED_environment_id_missing" in ENSURE
    assert "assert_create_env_argv_match" in ENSURE
    assert "audit_create_environment_output" in ENSURE
    assert "evaluate_create_command_pass" in ENSURE
    assert "P2_MIGRATION_CREATE_ENV_ARG_MATCH=true" in ENSURE
    assert "P2_MIGRATION_CREATE_COMMAND_PASS=true" in ENSURE
    assert "P2_MIGRATION_CREATE_ENV_OUTPUT_STATUS=" in ENSURE
    assert "BLOCKER_create_environment_mismatch" in ENSURE
    assert "BLOCKER_create_env_arg_mismatch" in ENSURE
    assert "plan_single_create_deploy(" in ENSURE
    assert "environment_id=environment_id," in ENSURE.replace(" ", "")
    # Missing returned env must not be treated as hard mismatch authority.
    assert "verify_create_environment_match" not in ENSURE
    assert "P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY=true" in ENSURE
    assert "evaluate_pinned_deploy_output" in ENSURE
    assert "P2_MIGRATION_DEPLOYMENT_LIST_AUTHORITY=false" in ENSURE


def test_activation_local_deploy_plan_and_source_identity(tmp_path: Path):
    ctx = build_migration_context(repo_root=ROOT, destination=tmp_path / "act", github_sha=SHA)
    identity = verify_context_source_identity(context_dir=ctx, expected_sha=SHA)
    assert identity["ok"] is True
    assert identity["P2_MIGRATION_POST_VAR_SOURCE_IDENTITY_PASS"] is True
    bad = verify_context_source_identity(context_dir=ctx, expected_sha="0" * 40)
    assert bad["ok"] is False
    plan = plan_activation_local_deploy(
        context_dir=ctx,
        project_id="aaaaaaaaaaaaaaaaaaaaaaaa",
        service_id="bbbbbbbbbbbbbbbbbbbbbbbb",
        environment_id=STAGING_ENV,
        repo_root=ROOT,
    )
    assert plan["argv"] == [
        "zeabur",
        "deploy",
        "--project-id",
        "aaaaaaaaaaaaaaaaaaaaaaaa",
        "--service-id",
        "bbbbbbbbbbbbbbbbbbbbbbbb",
        "--environment-id",
        STAGING_ENV,
        "-i=false",
        "--json",
    ]
    assert "--create" not in plan["argv"]
    assert plan["P2_MIGRATION_TOTAL_LOCAL_DEPLOY_COUNT"] == 2
    assert plan["P2_MIGRATION_SECOND_SERVICE_CREATED"] is False
    assert plan["exchange_write_call_count"] == 0


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
