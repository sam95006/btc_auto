#!/usr/bin/env python3
"""Create a run-scoped P2 migration service with ONE migration-context deploy.

Never calls shared _create_empty_cli() (repo-root / placeholder deploy).
Never reuses an existing same-name service.
Always targets an explicit ZEABUR_ENV_ID (no implicit first-environment fallback).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import tools.ci.ensure_demo_validation_zeabur_service as zeabur_svc
from tools.ci.p2_migration_bootstrap import (
    assert_create_env_argv_match,
    audit_create_environment_output,
    evaluate_create_command_pass,
    extract_service_id_from_create_output,
    plan_single_create_deploy,
    sanitize_bootstrap_failure_diagnostics,
    validate_migration_context,
)
from tools.ci.p2_migration_deployment_phase import evaluate_pinned_deploy_output
from tools.ci.p2_migration_service_identity import (
    MIGRATION_SERVICE_BASE_NAME,
    assert_distinct_migration_service,
    assert_run_scoped_service_name,
    build_run_scoped_migration_service_name,
    safe_service_id_prefix,
    safe_service_name_prefix,
)


def _forbidden_ids() -> set[str]:
    forbidden = {
        item.strip()
        for item in os.environ.get("FORBIDDEN_SERVICE_IDS", "").split(",")
        if item.strip()
    }
    learning_validation_id = (
        os.environ.get("LEARNING_VALIDATION_SERVICE_ID")
        or os.environ.get("ZEABUR_DEMO_VALIDATION_SERVICE_ID")
        or ""
    ).strip()
    if learning_validation_id:
        forbidden.add(learning_validation_id)
    preset = os.environ.get("PRESET_SERVICE_ID", "").strip()
    if preset:
        forbidden.add(preset)
    return forbidden


def _resolve_requested_name() -> tuple[str, str, str]:
    run_id = (os.environ.get("GITHUB_RUN_ID") or "").strip()
    run_attempt = (os.environ.get("GITHUB_RUN_ATTEMPT") or "").strip()
    explicit = (os.environ.get("P2_MIGRATION_SERVICE_NAME") or "").strip()
    if explicit:
        meta = assert_run_scoped_service_name(explicit, run_id=run_id, run_attempt=run_attempt)
        return explicit, meta["run_id"], meta["run_attempt"]
    if not run_id or not run_attempt:
        raise ValueError("run_scoped_service_name_or_run_identity_required")
    name = build_run_scoped_migration_service_name(run_id=run_id, run_attempt=run_attempt)
    assert_run_scoped_service_name(name, run_id=run_id, run_attempt=run_attempt)
    return name, run_id, run_attempt


def _exact_name_match(rows: list[dict], service_name: str) -> str:
    want = service_name.lower().replace("_", "-")
    for row in rows:
        name = zeabur_svc._service_name(row)
        sid = zeabur_svc._service_id(row)
        if name == want and sid:
            return sid
    return ""


def _list_services() -> list[dict]:
    try:
        rows = zeabur_svc._list_services_graphql()
        print(f"listed_services_graphql={len(rows)}", file=sys.stderr)
        return rows
    except Exception as exc:  # noqa: BLE001
        print(f"list_graphql_failed:{zeabur_svc._redact(str(exc))}", file=sys.stderr)
        rows = zeabur_svc._list_services_cli()
        print(f"listed_services_cli={len(rows)}", file=sys.stderr)
        return rows


def _create_with_migration_context(
    *,
    context_dir: Path,
    service_name: str,
    project_id: str,
    environment_id: str,
) -> tuple[str, int, str, dict]:
    plan = plan_single_create_deploy(
        context_dir=context_dir,
        service_name=service_name,
        project_id=project_id,
        environment_id=environment_id,
        repo_root=os.environ.get("GITHUB_WORKSPACE") or None,
    )
    print("P2_MIGRATION_SINGLE_DEPLOY_BOOTSTRAP=true", file=sys.stderr)
    print(f"P2_MIGRATION_BOOTSTRAP_DEPLOY_COUNT={plan['P2_MIGRATION_BOOTSTRAP_DEPLOY_COUNT']}", file=sys.stderr)
    print("P2_MIGRATION_CREATE_ENV_EXPLICIT=true", file=sys.stderr)
    print(f"bootstrap_cwd_prefix={str(plan['cwd'])[:48]}", file=sys.stderr)
    print(f"create_env_id_prefix={environment_id[:6]}", file=sys.stderr)

    arg_match = assert_create_env_argv_match(
        plan["argv"],
        expected_environment_id=environment_id,
    )
    if not arg_match["ok"]:
        print("P2_MIGRATION_CREATE_ENV_ARG_MATCH=false", file=sys.stderr)
        raise ValueError("create_env_arg_mismatch")
    print("P2_MIGRATION_CREATE_ENV_ARG_MATCH=true", file=sys.stderr)

    env = os.environ.copy()
    env["ZEABUR_TOKEN"] = zeabur_svc.TOKEN
    subprocess.run(
        ["zeabur", "auth", "login", "--token", zeabur_svc.TOKEN, "-i=false"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    proc = subprocess.run(
        plan["argv"],
        cwd=plan["cwd"],
        capture_output=True,
        text=True,
        env=env,
        timeout=900,
    )
    raw = (proc.stdout or "") + "\n" + (proc.stderr or "")
    print(f"create_deploy_exit={proc.returncode}", file=sys.stderr)
    print(f"create_deploy_head={zeabur_svc._redact(raw[:300])}", file=sys.stderr)
    output_audit = audit_create_environment_output(
        create_output=raw,
        expected_environment_id=environment_id,
    )
    print(
        f"P2_MIGRATION_CREATE_ENV_OUTPUT_STATUS={output_audit['P2_MIGRATION_CREATE_ENV_OUTPUT_STATUS']}",
        file=sys.stderr,
    )
    sid = (output_audit.get("service_id") or "").strip() or extract_service_id_from_create_output(raw)
    if not sid:
        # Exact-name re-list after create+deploy (service id only).
        try:
            rows = _list_services()
        except Exception as exc:  # noqa: BLE001
            print(f"relist_after_create_failed:{zeabur_svc._redact(str(exc))}", file=sys.stderr)
            rows = []
        sid = _exact_name_match(rows, service_name)
    return sid, proc.returncode, raw, output_audit


def main() -> int:
    if not os.environ.get("ZEABUR_TOKEN") or not os.environ.get("ZEABUR_PROJECT_ID"):
        print("missing_ZEABUR_TOKEN_or_PROJECT_ID", file=sys.stderr)
        return 2
    environment_id = (os.environ.get("ZEABUR_ENV_ID") or "").strip()
    if not environment_id:
        print("BLOCKED_environment_id_missing", file=sys.stderr)
        print("P2_MIGRATION_CREATE_ENV_EXPLICIT=false", file=sys.stderr)
        return 3
    context_raw = (os.environ.get("P2_MIGRATION_CONTEXT_DIR") or "").strip()
    if not context_raw:
        print("BLOCKED_migration_context_dir_required", file=sys.stderr)
        return 3
    context_dir = Path(context_raw)
    expected_sha = (os.environ.get("GITHUB_SHA") or "").strip() or None
    try:
        validate_migration_context(context_dir, expected_sha=expected_sha)
    except ValueError as exc:
        print(f"BLOCKED_{exc}", file=sys.stderr)
        return 3
    try:
        service_name, _run_id, _run_attempt = _resolve_requested_name()
    except ValueError as exc:
        print(f"BLOCKED_{exc}", file=sys.stderr)
        return 3
    if service_name == MIGRATION_SERVICE_BASE_NAME:
        print("BLOCKED_legacy_fixed_migration_service_name_forbidden", file=sys.stderr)
        return 3

    zeabur_svc.SERVICE_NAME = service_name
    zeabur_svc.TOKEN = (os.environ.get("ZEABUR_TOKEN") or "").strip()
    zeabur_svc.PROJECT_ID = (os.environ.get("ZEABUR_PROJECT_ID") or "").strip()
    forbidden = _forbidden_ids()
    zeabur_svc.FORBIDDEN_IDS = frozenset(forbidden)
    zeabur_svc.PRESET = ""

    print("P2_MIGRATION_RUN_SCOPED_SERVICE=true", file=sys.stderr)
    print(f"requested_service_name_prefix={safe_service_name_prefix(service_name)}", file=sys.stderr)
    print("uses_create_empty_cli=false", file=sys.stderr)
    print("P2_MIGRATION_CREATE_ENV_EXPLICIT=true", file=sys.stderr)

    try:
        rows = _list_services()
    except Exception as exc:  # noqa: BLE001
        print(f"list_cli_failed:{zeabur_svc._redact(str(exc))}", file=sys.stderr)
        return 4

    existing = _exact_name_match(rows, service_name)
    if existing:
        print("BLOCKER_run_scoped_service_already_exists", file=sys.stderr)
        print(f"existing_id_prefix={safe_service_id_prefix(existing)}", file=sys.stderr)
        print("P2_MIGRATION_PREVIOUS_SERVICE_REUSED=false", file=sys.stderr)
        return 6

    legacy = _exact_name_match(rows, MIGRATION_SERVICE_BASE_NAME)
    if legacy:
        print(
            f"legacy_fixed_service_present_disarmed_only id_prefix={safe_service_id_prefix(legacy)}",
            file=sys.stderr,
        )

    # Intentionally never call zeabur_svc._create_empty() or _create_empty_cli().
    try:
        service_id, create_exit, create_raw, output_audit = _create_with_migration_context(
            context_dir=context_dir,
            service_name=service_name,
            project_id=zeabur_svc.PROJECT_ID,
            environment_id=environment_id,
        )
    except ValueError as exc:
        if str(exc) == "create_env_arg_mismatch":
            print("BLOCKER_create_env_arg_mismatch", file=sys.stderr)
            return 7
        print(f"BLOCKED_{exc}", file=sys.stderr)
        return 3
    service_id = (service_id or "").strip()

    if output_audit.get("blocks_create"):
        print("P2_MIGRATION_CREATE_ENV_OUTPUT_STATUS=MISMATCH", file=sys.stderr)
        print(
            f"create_env_output_mismatch expected_prefix={environment_id[:6]} "
            f"returned_prefix={(output_audit.get('environment_id') or 'missing')[:6]}",
            file=sys.stderr,
        )
        diag = sanitize_bootstrap_failure_diagnostics(
            create_deploy_exit=create_exit,
            create_deploy_output=create_raw,
            service_id=service_id or None,
            service_name=service_name,
            readiness_attempts=0,
            not_running_count=0,
            current_image_positive_proof_count=0,
        )
        print(f"bootstrap_diag={diag}", file=sys.stderr)
        print("BLOCKER_create_environment_mismatch", file=sys.stderr)
        return 7

    print(
        f"P2_MIGRATION_CREATE_ENV_OUTPUT_STATUS={output_audit.get('P2_MIGRATION_CREATE_ENV_OUTPUT_STATUS')}",
        file=sys.stderr,
    )

    command_pass = evaluate_create_command_pass(
        create_exit=create_exit,
        service_id=service_id,
        create_output=create_raw,
    )
    if not command_pass["ok"]:
        print("P2_MIGRATION_CREATE_COMMAND_PASS=false", file=sys.stderr)
        diag = sanitize_bootstrap_failure_diagnostics(
            create_deploy_exit=create_exit,
            create_deploy_output=create_raw,
            service_id=service_id or None,
            service_name=service_name,
            readiness_attempts=0,
            not_running_count=0,
            current_image_positive_proof_count=0,
        )
        print(f"bootstrap_diag={diag}", file=sys.stderr)
        if not service_id:
            print("BLOCKER_migration_service_id_unresolved", file=sys.stderr)
            return 5
        print("BLOCKER_create_command_failed", file=sys.stderr)
        return 8

    print("P2_MIGRATION_CREATE_COMMAND_PASS=true", file=sys.stderr)
    print("P2_MIGRATION_CREATE_ENV_ARG_MATCH=true", file=sys.stderr)

    pinned = evaluate_pinned_deploy_output(
        deploy_output=create_raw,
        deploy_exit=create_exit,
        expected_service_id=service_id,
        expected_environment_id=environment_id,
        expected_project_id=zeabur_svc.PROJECT_ID,
        phase="bootstrap",
    )
    if not pinned["ok"]:
        print("P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY=true", file=sys.stderr)
        print("P2_MIGRATION_DEPLOYMENT_LIST_AUTHORITY=false", file=sys.stderr)
        print(
            f"P2_ZEABUR_DIRECT_UPLOAD_MARKER_PRESENT={str(pinned.get('P2_ZEABUR_DIRECT_UPLOAD_MARKER_PRESENT', False)).lower()}",
            file=sys.stderr,
        )
        print("P2_ZEABUR_DEPLOYMENT_ID_DIRECT_FROM_UPLOAD=false", file=sys.stderr)
        diag = sanitize_bootstrap_failure_diagnostics(
            create_deploy_exit=create_exit,
            create_deploy_output=create_raw,
            service_id=service_id or None,
            service_name=service_name,
            readiness_attempts=0,
            not_running_count=0,
            current_image_positive_proof_count=0,
        )
        print(f"bootstrap_diag={diag}", file=sys.stderr)
        print("BLOCKER_bootstrap_deploy_missing_direct_deployment_id", file=sys.stderr)
        return 9

    bootstrap_deployment_id = pinned["deployment_id"]
    print("P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY=true", file=sys.stderr)
    print("P2_MIGRATION_DEPLOYMENT_LIST_AUTHORITY=false", file=sys.stderr)
    print(
        f"P2_ZEABUR_DIRECT_UPLOAD_MARKER_PRESENT={str(pinned.get('P2_ZEABUR_DIRECT_UPLOAD_MARKER_PRESENT', False)).lower()}",
        file=sys.stderr,
    )
    print("P2_ZEABUR_DEPLOYMENT_ID_DIRECT_FROM_UPLOAD=true", file=sys.stderr)
    print(f"P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_ID={bootstrap_deployment_id}", file=sys.stderr)
    print(f"bootstrap_deployment_id_prefix={bootstrap_deployment_id[:6]}", file=sys.stderr)

    learning_validation_id = (
        os.environ.get("LEARNING_VALIDATION_SERVICE_ID")
        or os.environ.get("ZEABUR_DEMO_VALIDATION_SERVICE_ID")
        or ""
    ).strip()
    try:
        identity = assert_distinct_migration_service(
            service_id,
            learning_validation_service_id=learning_validation_id,
            forbidden_service_ids=forbidden,
            service_name=service_name,
        )
    except ValueError as exc:
        print(f"BLOCKED_{exc}", file=sys.stderr)
        return 3

    print("P2_MIGRATION_PREVIOUS_SERVICE_REUSED=false", file=sys.stderr)
    print("P2_MIGRATION_SINGLE_DEPLOY_BOOTSTRAP=true", file=sys.stderr)
    print("P2_MIGRATION_BOOTSTRAP_DEPLOY_COUNT=1", file=sys.stderr)
    print("P2_MIGRATION_SERVICE_CREATE_COUNT=1", file=sys.stderr)
    print("P2_MIGRATION_BOOTSTRAP_LOCAL_DEPLOY_COUNT=1", file=sys.stderr)
    print("P2_MIGRATION_SECOND_SERVICE_CREATED=false", file=sys.stderr)
    print("P2_MIGRATION_CREATE_ENV_EXPLICIT=true", file=sys.stderr)
    print(
        f"migration_service_created=true id_prefix={identity['migration_service_id_prefix']} "
        f"name_prefix={safe_service_name_prefix(service_name)}",
        file=sys.stderr,
    )
    print(
        f"learning_validation_not_reused=true id_prefix={identity['learning_validation_service_id_prefix']}",
        file=sys.stderr,
    )
    print(service_id, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
