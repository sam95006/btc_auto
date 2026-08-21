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


def test_get_and_log_service_name_intersection_selects_service_name():
    get_help = "Usage: zeabur deployment get --env-id <id> --service-name <name>"
    log_help = "Usage: zeabur deployment log -t=build|runtime --env-id <id> --service-name <name>"
    parsed = parse_zeabur_deployment_help(get_help=get_help, log_help=log_help, list_help="")
    assert parsed["preferred_selector"] == "service-name"
    assert parsed["get_supports_service_name"] is True
    assert parsed["log_supports_service_name"] is True
    assert parsed["supports_deployment_list"] is False


def test_get_service_name_without_log_support_is_not_preferred():
    parsed = parse_zeabur_deployment_help(
        get_help="get --env-id X --service-name Y",
        log_help="log --env-id X --service-id Z",
    )
    assert parsed["preferred_selector"] != "service-name"
    assert parsed["preferred_selector"] == "none"


def test_service_id_only_when_both_get_and_log_prove_it():
    parsed = parse_zeabur_deployment_help(
        get_help="get --env-id X --service-id Y",
        log_help="log --env-id X --service-id Y",
    )
    assert parsed["preferred_selector"] == "service-id"
    assert parsed["supports_service_id"] is True


def test_deployment_list_unsupported_still_allows_control_path():
    parsed = parse_zeabur_deployment_help(
        get_help="get --env-id X --service-name Y",
        log_help="log --env-id X --service-name Y",
        list_help="",
        list_help_exit=2,
    )
    assert parsed["preferred_selector"] == "service-name"
    assert parsed["supports_deployment_list"] is False


def test_workflow_probes_get_and_log_help_and_prints_blocker():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "zeabur deployment get --help" in source
    assert "zeabur deployment log --help" in source
    assert "--parse-get-help-file" in source
    assert "--parse-log-help-file" in source
    assert ">/tmp/zeabur_deployment_cli_contract.json" in source
    assert "| tee /tmp/zeabur_deployment_cli_contract.json" not in source
    assert "BLOCKER_zeabur_deployment_cli_selector_unsupported" in source
    assert "deployment_list_skipped=true" in source
    assert "--service-name \"$SERVICE_NAME\"" in source
    assert "deployment_get_exit=" in source
    assert "--deployment-get-exit" in source
    # Parent help must not be the selector authority.
    wait = source[
        source.index("Wait for Zeabur deployment RUNNING before service-exec probes") : source.index(
            "Wait for fresh migration service baked SHA readiness"
        )
    ]
    assert "zeabur deployment --help" not in wait or "never use it for selector" in wait
    assert "zeabur deployment get --help" in wait
    readiness = source[
        source.index("Wait for fresh migration service baked SHA readiness") : source.index(
            "Require final disarmed runtime with ledger DSN"
        )
    ]
    assert "MAX_ATTEMPTS=12" in readiness
