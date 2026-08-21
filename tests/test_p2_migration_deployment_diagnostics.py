"""Deployment metadata diagnostics: veto-only; never authorize migration exec."""
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
CONTAINER_IMAGE_BUILD_MSG = (
    "no build logs available: this service was started from a container "
    "image and was not built on Zeabur"
)


def test_status_running_does_not_authorize_migration_exec():
    classified = classify_deployment_snapshot(deployment_get_raw='{"status":"RUNNING"}')
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "RUNNING"
    assert classified["service_exec_allowed"] is False
    assert classified["proceed_to_operational_probe"] is True
    assert classified["metadata_veto"] is False


def test_status_ready_proceeds_to_operational_not_exec():
    classified = classify_deployment_snapshot(deployment_get_raw='{"status":"READY"}')
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "RUNNING"
    assert classified["service_exec_allowed"] is False
    assert classified["proceed_to_operational_probe"] is True


def test_status_not_running_metadata_does_not_veto():
    classified = classify_deployment_snapshot(deployment_get_raw='{"status":"NOT_RUNNING"}')
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "NOT_RUNNING"
    assert classified["metadata_veto"] is False
    assert classified["proceed_to_operational_probe"] is True
    assert classified["service_exec_allowed"] is False


def test_raw_not_running_sentence_never_running():
    classified = classify_deployment_snapshot(
        deployment_get_raw="ERROR execute command failed\nThis service is not in the running state\n",
        deployment_get_exit=0,
    )
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] != "RUNNING"
    assert classified["service_exec_allowed"] is False


def test_status_inactive_is_suspended_veto():
    classified = classify_deployment_snapshot(deployment_get_raw='{"status":"INACTIVE"}')
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "SUSPENDED"
    assert classified["metadata_veto"] is True
    assert classified["fail_closed"] is True
    assert classified["proceed_to_operational_probe"] is False
    assert normalize_status_token("INACTIVE") == "INACTIVE"


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
    assert classified["proceed_to_operational_probe"] is True


def test_malformed_json_containing_running_never_running():
    classified = classify_deployment_snapshot(
        deployment_get_raw="not-json but status running READY ACTIVE",
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
    assert classified["proceed_to_operational_probe"] is False
    assert classified["service_exec_allowed"] is False


def test_failed_fails_closed_with_build_tail():
    classified = classify_deployment_snapshot(
        deployment_get_raw='{"status":"FAILED"}',
        build_log_raw="BUILD_FAILED\nsecret postgresql://user:pass@host/db\n",
    )
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "FAILED"
    assert classified["fail_closed"] is True
    assert classified["metadata_veto"] is True
    assert classified["proceed_to_operational_probe"] is False
    assert "postgresql://***REDACTED***" in classified["P2_MIGRATION_BUILD_LOG_TAIL"]


def test_building_then_unknown_proceeds_to_operational():
    outs = [
        {"deployment_get": '{"status":"BUILDING"}', "build_log": "pip", "runtime_log": "", "deployment_list": "[]"},
        {"deployment_get": '{"status":"DEPLOYING"}', "build_log": "done", "runtime_log": "starting", "deployment_list": "[]"},
        {"deployment_get": "{}", "build_log": "", "runtime_log": "", "deployment_list": "[]", "service_get": '{"Status":"UNKNOWN"}'},
    ]
    calls = {"n": 0}

    def probe(_attempt: int) -> dict:
        idx = min(calls["n"], len(outs) - 1)
        calls["n"] += 1
        return outs[idx]

    result = wait_for_deployment_running(probe=probe, max_attempts=5, sleep=lambda _s: None)
    assert result["proceed_to_operational_probe"] is True
    assert result["service_exec_allowed"] is False
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


def test_service_id_preferred_when_both_id_and_name_supported():
    parsed = parse_zeabur_deployment_help(
        get_help="get --env-id X --service-id Y --service-name Z",
        log_help="log --env-id X --service-id Y --service-name Z",
    )
    assert parsed["preferred_selector"] == "service-id"


def test_service_id_not_selected_when_only_get_supports_it():
    parsed = parse_zeabur_deployment_help(
        get_help="get --env-id X --service-id Y --service-name Z",
        log_help="log --env-id X --service-name Z",
    )
    assert parsed["preferred_selector"] == "none"


def test_service_name_and_owner_project_flags_never_selected_without_service_id():
    parsed = parse_zeabur_deployment_help(
        get_help="get --env-id X --service-name Y --owner-name O --project-name P",
        log_help="log --env-id X --service-name Y --owner-name O --project-name P",
    )
    assert parsed["preferred_selector"] == "none"


def test_service_id_only_when_both_get_and_log_prove_it():
    parsed = parse_zeabur_deployment_help(
        get_help="get --env-id X --service-id Y",
        log_help="log --env-id X --service-id Y",
    )
    assert parsed["preferred_selector"] == "service-id"


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
    )
    assert classified["cli_semantic_error"] is True
    assert classified["metadata_veto"] is True
    assert classified["fail_closed"] is True
    assert classified["proceed_to_operational_probe"] is False


def test_exit0_owner_project_name_error_never_building():
    classified = classify_deployment_snapshot(
        deployment_get_raw=(
            "failed to get service: either id or ownerName, projectName, and name must be specified"
        ),
        deployment_get_exit=0,
    )
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "CLI_ERROR"
    assert classified["wait_for_deployment"] is False


def test_semantic_cli_error_stops_wait_on_first_attempt():
    calls = {"n": 0}

    def probe(_attempt: int) -> dict:
        calls["n"] += 1
        return {
            "deployment_get": "failed to get service: either id or ownerName, projectName, and name must be specified",
            "deployment_get_exit": 0,
        }

    result = wait_for_deployment_running(probe=probe, max_attempts=24, sleep=lambda _s: None)
    assert result["proceed_to_operational_probe"] is False
    assert result["attempts"] == 1


def test_workflow_metadata_veto_then_operational_readiness():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "Metadata diagnostic and explicit-negative veto" in source
    assert "Operational service-exec readiness" in source
    assert "Wait for Zeabur deployment RUNNING before service-exec probes" not in source
    assert "Wait for fresh migration service baked SHA readiness" not in source
    meta = source[
        source.index("Metadata diagnostic and explicit-negative veto") : source.index(
            "Operational service-exec readiness"
        )
    ]
    assert 'zeabur service get --id "$SERVICE_ID"' in meta
    assert "proceed_to_operational_probe" in meta or "P2_MIGRATION_METADATA_PROCEED_TO_OPERATIONAL" in meta
    assert "--service-name" not in meta
    op = source[
        source.index("Operational service-exec readiness") : source.index(
            "Require final disarmed runtime with ledger DSN"
        )
    ]
    assert "P2_MIGRATION_OPERATIONAL_READINESS_PASS=true" in op
    assert "current_image_streak=" in op
    assert "MAX_ATTEMPTS=12" in op
    assert "STREAK_NEEDED=3" in op


def test_container_image_build_log_na_is_informational_not_failure():
    classified = classify_deployment_snapshot(
        deployment_get_raw="{}",
        build_log_raw=CONTAINER_IMAGE_BUILD_MSG,
    )
    assert classified["P2_MIGRATION_CONTAINER_IMAGE_SERVICE"] is True
    assert classified["cli_semantic_error"] is False
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] != "RUNNING"


def test_deployment_unknown_proceeds_without_metadata_authority():
    classified = classify_deployment_snapshot(
        deployment_get_raw="{}",
        build_log_raw=CONTAINER_IMAGE_BUILD_MSG,
        service_get_raw='{"Status":"UNKNOWN"}',
        service_get_exit=0,
    )
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "UNKNOWN"
    assert classified["P2_MIGRATION_SERVICE_STATUS"] == "UNKNOWN"
    assert classified["P2_MIGRATION_SERVICE_STATUS_AUTHORITY"] is False
    assert classified["service_exec_allowed"] is False
    assert classified["proceed_to_operational_probe"] is True
    assert classified["metadata_veto"] is False


def test_deployment_failed_blocks_even_if_service_running():
    classified = classify_deployment_snapshot(
        deployment_get_raw='{"status":"FAILED"}',
        service_get_raw='{"status":"RUNNING"}',
    )
    assert classified["metadata_veto"] is True
    assert classified["proceed_to_operational_probe"] is False
    assert classified["service_exec_allowed"] is False


def test_service_malformed_json_with_running_never_authorizes():
    classified = classify_deployment_snapshot(
        deployment_get_raw="{}",
        service_get_raw="not-json RUNNING READY ACTIVE",
        service_get_exit=0,
    )
    assert classified["service_exec_allowed"] is False
    assert classified["P2_MIGRATION_SERVICE_STATUS_AUTHORITY"] is False
