"""Deployment-status diagnostics for P2 migration (no live Zeabur calls)."""
from __future__ import annotations

from pathlib import Path

from tools.ci.p2_migration_deployment_diagnostics import (
    classify_deployment_snapshot,
    normalize_status_token,
    parse_zeabur_deployment_help,
    sanitize_log_tail,
    wait_for_deployment_running,
)

WORKFLOW = Path(".github/workflows/founder_approved_staging_postgres_p2_migration.yml")


def test_status_running_allows_exec():
    classified = classify_deployment_snapshot(deployment_get_raw='{"status":"RUNNING"}')
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "RUNNING"
    assert classified["service_exec_allowed"] is True


def test_status_ready_maps_to_running_when_structured():
    classified = classify_deployment_snapshot(deployment_get_raw='{"status":"READY"}')
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "RUNNING"
    assert classified["service_exec_allowed"] is True


def test_status_not_running_forbids_exec():
    classified = classify_deployment_snapshot(deployment_get_raw='{"status":"NOT_RUNNING"}')
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "NOT_RUNNING"
    assert classified["service_exec_allowed"] is False


def test_raw_not_running_sentence_never_running():
    classified = classify_deployment_snapshot(
        deployment_get_raw="ERROR execute command failed\nThis service is not in the running state\n",
        deployment_get_exit=0,
    )
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] != "RUNNING"
    assert classified["service_exec_allowed"] is False


def test_status_inactive_is_suspended_not_active():
    classified = classify_deployment_snapshot(deployment_get_raw='{"status":"INACTIVE"}')
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "SUSPENDED"
    assert classified["service_exec_allowed"] is False
    assert normalize_status_token("INACTIVE") == "INACTIVE"
    assert "ACTIVE" != normalize_status_token("INACTIVE")


def test_status_not_ready_never_running():
    classified = classify_deployment_snapshot(deployment_get_raw='{"status":"NOT_READY"}')
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "NOT_RUNNING"
    assert classified["service_exec_allowed"] is False


def test_cli_nonzero_exit_with_running_word_never_running():
    classified = classify_deployment_snapshot(
        deployment_get_raw="usage error: service is running",
        deployment_get_exit=2,
    )
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "UNKNOWN"
    assert classified["service_exec_allowed"] is False
    assert classified["deployment_get_exit"] == 2


def test_malformed_json_containing_running_never_running():
    classified = classify_deployment_snapshot(
        deployment_get_raw='not-json but status running READY ACTIVE',
        deployment_get_exit=0,
    )
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] != "RUNNING"
    assert classified["service_exec_allowed"] is False


def test_empty_status_never_positive_running():
    classified = classify_deployment_snapshot()
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] in {"BUILDING", "UNKNOWN"}
    assert classified["service_exec_allowed"] is False


def test_building_waits_and_does_not_allow_service_exec():
    classified = classify_deployment_snapshot(
        deployment_get_raw='{"status":"BUILDING"}',
        build_log_raw="Step 1/8 : FROM python",
    )
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "BUILDING"
    assert classified["wait_for_deployment"] is True
    assert classified["service_exec_allowed"] is False


def test_failed_fails_closed_with_build_tail():
    classified = classify_deployment_snapshot(
        deployment_get_raw='{"status":"FAILED"}',
        build_log_raw="BUILD_FAILED\nsecret postgresql://user:pass@host/db\n",
    )
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "FAILED"
    assert classified["fail_closed"] is True
    assert classified["service_exec_allowed"] is False
    assert "postgresql://***REDACTED***" in classified["P2_MIGRATION_BUILD_LOG_TAIL"]


def test_building_then_running_defers_service_exec_until_running():
    outs = [
        {"deployment_get": '{"status":"BUILDING"}', "build_log": "pip", "runtime_log": "", "deployment_list": "[]"},
        {"deployment_get": '{"status":"DEPLOYING"}', "build_log": "done", "runtime_log": "starting", "deployment_list": "[]"},
        {"deployment_get": '{"status":"RUNNING"}', "build_log": "done", "runtime_log": "up", "deployment_list": "[]"},
    ]
    calls = {"n": 0}

    def probe(_attempt: int) -> dict:
        idx = min(calls["n"], len(outs) - 1)
        calls["n"] += 1
        return outs[idx]

    result = wait_for_deployment_running(probe=probe, max_attempts=5, sleep=lambda _s: None)
    assert result["ready_for_service_exec"] is True
    assert result["attempts"] == 3


def test_sanitize_log_tail_redacts_tokens():
    raw = "Bearer abcdefghijklmnopqrstuvwxyz0123456789XXXX postgresql://a:b@c/d"
    out = sanitize_log_tail(raw)
    assert "Bearer ***REDACTED***" in out
    assert "postgresql://***REDACTED***" in out


def test_parent_help_with_subcommands_only_does_not_select_selector():
    parent = """
    Usage: zeabur deployment [command]
    Available Commands:
      get   Get deployment
      log   Show deployment logs
      list  List deployments
    """
    parsed = parse_zeabur_deployment_help(parent_help=parent, get_help="", log_help="", list_help="")
    assert parsed["preferred_selector"] == "none"
    assert parsed["supports_service_name"] is False
    assert parsed["supports_service_id"] is False


def test_service_id_preferred_when_both_id_and_name_supported():
    get_help = "get --env-id X --service-id Y --service-name Z"
    log_help = "log --env-id X --service-id Y --service-name Z"
    parsed = parse_zeabur_deployment_help(get_help=get_help, log_help=log_help)
    assert parsed["preferred_selector"] == "service-id"


def test_service_id_not_selected_when_only_get_supports_it():
    parsed = parse_zeabur_deployment_help(
        get_help="get --env-id X --service-id Y --service-name Z",
        log_help="log --env-id X --service-name Z",
    )
    assert parsed["preferred_selector"] == "none"


def test_service_name_and_owner_project_flags_never_selected_without_service_id():
    get_help = "get --env-id X --service-name Y --owner-name O --project-name P"
    log_help = "log --env-id X --service-name Y --owner-name O --project-name P"
    parsed = parse_zeabur_deployment_help(get_help=get_help, log_help=log_help)
    assert parsed["preferred_selector"] == "none"
    assert parsed["supports_service_name"] is False


def test_service_id_only_when_both_get_and_log_prove_it():
    parsed = parse_zeabur_deployment_help(
        get_help="get --env-id X --service-id Y",
        log_help="log --env-id X --service-id Y",
    )
    assert parsed["preferred_selector"] == "service-id"
    assert parsed["supports_service_id"] is True


def test_deployment_list_unsupported_still_allows_service_id_control_path():
    parsed = parse_zeabur_deployment_help(
        get_help="get --env-id X --service-id Y",
        log_help="log --env-id X --service-id Y",
        list_help="",
        list_help_exit=2,
    )
    assert parsed["preferred_selector"] == "service-id"
    assert parsed["supports_deployment_list"] is False


def test_exit0_failed_to_get_service_is_cli_error_fail_closed():
    classified = classify_deployment_snapshot(
        deployment_get_raw="failed to get service: get service<nexus-p2m7-1> failed",
        deployment_get_exit=0,
        deployment_list_exit=0,
        build_log_exit=0,
        runtime_log_exit=0,
    )
    assert classified["cli_command_failed"] is True
    assert classified["cli_semantic_error"] is True
    assert classified["fail_closed"] is True
    assert classified["wait_for_deployment"] is False
    assert classified["service_exec_allowed"] is False
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "CLI_ERROR"


def test_exit0_owner_project_name_error_never_building():
    classified = classify_deployment_snapshot(
        deployment_get_raw=(
            "failed to get service: either id or ownerName, projectName, and name must be specified"
        ),
        deployment_get_exit=0,
    )
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] != "BUILDING"
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "CLI_ERROR"
    assert classified["wait_for_deployment"] is False


def test_semantic_cli_error_stops_wait_on_first_attempt():
    calls = {"n": 0}

    def probe(_attempt: int) -> dict:
        calls["n"] += 1
        return {
            "deployment_get": "failed to get service: either id or ownerName, projectName, and name must be specified",
            "deployment_get_exit": 0,
            "deployment_list": "",
            "deployment_list_exit": 0,
            "build_log": "",
            "build_log_exit": 0,
            "runtime_log": "",
            "runtime_log_exit": 0,
        }

    result = wait_for_deployment_running(probe=probe, max_attempts=24, sleep=lambda _s: None)
    assert result["ready_for_service_exec"] is False
    assert result["attempts"] == 1
    assert calls["n"] == 1
    assert result["P2_MIGRATION_DEPLOYMENT_STATUS"] == "CLI_ERROR"


def test_workflow_service_id_only_no_service_name_fallback():
    source = WORKFLOW.read_text(encoding="utf-8")
    wait = source[
        source.index("Wait for Zeabur deployment RUNNING before service-exec probes") : source.index(
            "Wait for fresh migration service baked SHA readiness"
        )
    ]
    assert "P2_MIGRATION_DEPLOYMENT_SELECTOR=" in wait
    assert 'if [ "$PREFERRED" != "service-id" ]' in wait
    assert "BLOCKER_zeabur_deployment_cli_selector_unsupported" in wait
    assert 'zeabur deployment get --service-id "$SERVICE_ID"' in wait
    assert 'zeabur service get --id "$SERVICE_ID"' in wait
    assert 'zeabur deployment log -t=build --service-id "$SERVICE_ID"' in wait
    assert 'zeabur deployment log -t=runtime --service-id "$SERVICE_ID"' in wait
    assert "--service-get" in wait
    assert "service_get_exit=" in wait
    assert "--service-name" not in wait
    assert 'elif [ "$PREFERRED" = "service-name" ]' not in wait
    assert "deployment_list_skipped=true" in wait
    readiness = source[
        source.index("Wait for fresh migration service baked SHA readiness") : source.index(
            "Require final disarmed runtime with ledger DSN"
        )
    ]
    assert "MAX_ATTEMPTS=12" in readiness


CONTAINER_IMAGE_BUILD_MSG = (
    "no build logs available: this service was started from a container "
    "image and was not built on Zeabur"
)


def test_container_image_build_log_na_is_informational_not_failure():
    classified = classify_deployment_snapshot(
        deployment_get_raw="{}",
        deployment_get_exit=0,
        build_log_raw=CONTAINER_IMAGE_BUILD_MSG,
        build_log_exit=0,
    )
    assert classified["P2_MIGRATION_CONTAINER_IMAGE_SERVICE"] is True
    assert classified["P2_MIGRATION_BUILD_LOG_NOT_APPLICABLE"] is True
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] != "FAILED"
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] != "CLI_ERROR"
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] != "RUNNING"
    assert classified["service_exec_allowed"] is False
    assert classified["cli_semantic_error"] is False


def test_deployment_unknown_service_running_authorizes():
    classified = classify_deployment_snapshot(
        deployment_get_raw="{}",
        deployment_get_exit=0,
        build_log_raw=CONTAINER_IMAGE_BUILD_MSG,
        service_get_raw='{"status":"RUNNING"}',
        service_get_exit=0,
    )
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "UNKNOWN"
    assert classified["P2_MIGRATION_SERVICE_STATUS"] == "RUNNING"
    assert classified["P2_MIGRATION_SERVICE_STATUS_AUTHORITY"] is True
    assert classified["service_exec_allowed"] is True
    assert classified["wait_for_deployment"] is False


def test_deployment_unknown_service_deploying_waits():
    classified = classify_deployment_snapshot(
        deployment_get_raw="{}",
        deployment_get_exit=0,
        service_get_raw='{"status":"DEPLOYING"}',
        service_get_exit=0,
    )
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "UNKNOWN"
    assert classified["wait_for_deployment"] is True
    assert classified["service_exec_allowed"] is False


def test_deployment_failed_blocks_even_if_service_running():
    classified = classify_deployment_snapshot(
        deployment_get_raw='{"status":"FAILED"}',
        deployment_get_exit=0,
        service_get_raw='{"status":"RUNNING"}',
        service_get_exit=0,
    )
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "FAILED"
    assert classified["fail_closed"] is True
    assert classified["service_exec_allowed"] is False
    assert classified["P2_MIGRATION_SERVICE_STATUS_AUTHORITY"] is False


def test_service_malformed_json_with_running_never_authorizes():
    classified = classify_deployment_snapshot(
        deployment_get_raw="{}",
        deployment_get_exit=0,
        service_get_raw="not-json RUNNING READY ACTIVE",
        service_get_exit=0,
    )
    assert classified["service_exec_allowed"] is False
    assert classified["P2_MIGRATION_SERVICE_STATUS_AUTHORITY"] is False


def test_service_structured_inactive_never_running():
    classified = classify_deployment_snapshot(
        deployment_get_raw="{}",
        service_get_raw='{"status":"INACTIVE"}',
        service_get_exit=0,
    )
    assert classified["service_exec_allowed"] is False
    assert classified["P2_MIGRATION_SERVICE_STATUS"] == "INACTIVE"


def test_service_structured_not_running_never_running():
    classified = classify_deployment_snapshot(
        deployment_get_raw="{}",
        service_get_raw='{"status":"NOT_RUNNING"}',
        service_get_exit=0,
    )
    assert classified["service_exec_allowed"] is False
    assert classified["P2_MIGRATION_SERVICE_STATUS"] == "NOT_RUNNING"


def test_service_running_proceeds_to_baked_sha_gate():
    classified = classify_deployment_snapshot(
        deployment_get_raw='{"id":"dep1"}',
        deployment_get_exit=0,
        build_log_raw=CONTAINER_IMAGE_BUILD_MSG,
        service_get_raw='{"Status":"RUNNING"}',
        service_get_exit=0,
    )
    assert classified["service_exec_allowed"] is True
    assert classified["P2_MIGRATION_SERVICE_STATUS_AUTHORITY"] is True
    assert classified["gate_status"] == "RUNNING"