"""Deployment-status diagnostics for P2 migration (no live Zeabur calls)."""
from __future__ import annotations

import json
from pathlib import Path

from tools.ci.p2_migration_deployment_diagnostics import (
    classify_deployment_snapshot,
    sanitize_log_tail,
    wait_for_deployment_running,
)

WORKFLOW = Path(".github/workflows/founder_approved_staging_postgres_p2_migration.yml")


def test_building_waits_and_does_not_allow_service_exec():
    classified = classify_deployment_snapshot(
        deployment_get_raw='{"status":"BUILDING"}',
        build_log_raw="Step 1/8 : FROM python",
    )
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "BUILDING"
    assert classified["wait_for_deployment"] is True
    assert classified["service_exec_allowed"] is False
    assert classified["exchange_write_call_count"] == 0


def test_running_allows_service_exec():
    classified = classify_deployment_snapshot(deployment_get_raw='{"status":"RUNNING"}')
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "RUNNING"
    assert classified["service_exec_allowed"] is True
    assert classified["P2_MIGRATION_BUILD_STATUS"] == "READY"


def test_failed_fails_closed_with_build_tail():
    classified = classify_deployment_snapshot(
        deployment_get_raw='{"status":"FAILED"}',
        build_log_raw="BUILD_FAILED\nsecret postgresql://user:pass@host/db\n",
    )
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "FAILED"
    assert classified["fail_closed"] is True
    assert classified["service_exec_allowed"] is False
    assert "postgresql://***REDACTED***" in classified["P2_MIGRATION_BUILD_LOG_TAIL"]
    assert "pass@" not in classified["P2_MIGRATION_BUILD_LOG_TAIL"]


def test_building_then_running_defers_service_exec_until_running():
    outs = [
        {
            "deployment_get": '{"status":"BUILDING"}',
            "build_log": "pip install ...",
            "runtime_log": "",
            "deployment_list": "[]",
        },
        {
            "deployment_get": '{"status":"DEPLOYING"}',
            "build_log": "done",
            "runtime_log": "starting",
            "deployment_list": "[]",
        },
        {
            "deployment_get": '{"status":"RUNNING"}',
            "build_log": "done",
            "runtime_log": "service_mode=P2_MIGRATION_0007",
            "deployment_list": "[]",
        },
    ]
    calls = {"n": 0}

    def probe(_attempt: int) -> dict:
        idx = min(calls["n"], len(outs) - 1)
        calls["n"] += 1
        return outs[idx]

    result = wait_for_deployment_running(probe=probe, max_attempts=5, sleep=lambda _s: None)
    assert result["ready_for_service_exec"] is True
    assert result["attempts"] == 3
    assert [row["P2_MIGRATION_DEPLOYMENT_STATUS"] for row in result["history"]] == [
        "BUILDING",
        "DEPLOYING",
        "RUNNING",
    ]


def test_unknown_fails_closed_without_service_exec():
    classified = classify_deployment_snapshot(
        deployment_get_raw='{"unexpected":"shape"}',
        build_log_raw="noise",
        runtime_log_raw="",
    )
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "UNKNOWN"
    assert classified["fail_closed"] is True
    assert classified["service_exec_allowed"] is False


def test_empty_snapshot_waits_as_building_not_instant_unknown():
    classified = classify_deployment_snapshot()
    assert classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "BUILDING"
    assert classified["wait_for_deployment"] is True
    assert classified["service_exec_allowed"] is False


def test_sanitize_log_tail_redacts_tokens():
    raw = "Bearer abcdefghijklmnopqrstuvwxyz0123456789XXXX postgresql://a:b@c/d"
    out = sanitize_log_tail(raw)
    assert "Bearer ***REDACTED***" in out
    assert "postgresql://***REDACTED***" in out
    assert "a:b@c/d" not in out


def test_workflow_collects_deployment_diagnostics_before_service_exec():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "Wait for Zeabur deployment RUNNING before service-exec probes" in source
    assert "zeabur deployment get" in source
    assert "zeabur deployment log -t=build" in source
    assert "zeabur deployment log -t=runtime" in source
    assert "p2_migration_deployment_diagnostics" in source
    assert "P2_MIGRATION_DEPLOYMENT_STATUS" in source
    assert "P2_MIGRATION_BUILD_LOG_TAIL" in source
    assert "P2_MIGRATION_RUNTIME_LOG_TAIL" in source
    assert source.index("Wait for Zeabur deployment RUNNING before service-exec probes") < source.index(
        "Wait for fresh migration service baked SHA readiness"
    )
    # Do not enlarge the baked-SHA service-exec attempt budget in this change.
    readiness = source[
        source.index("Wait for fresh migration service baked SHA readiness") : source.index(
            "Require final disarmed runtime with ledger DSN"
        )
    ]
    assert "MAX_ATTEMPTS=12" in readiness
