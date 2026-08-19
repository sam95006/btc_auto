from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.ci.p1_zeabur_transport import (
    EXECUTE_COMMAND_QUERY,
    build_execute_command_request,
    evidence_download_ready,
    parse_execute_command_response,
    parse_recovery_evidence,
    parse_runner_stdout_diagnostic,
    recovery_gate_may_pass,
    transport_probe_matches,
    unique_evidence_path,
    unique_transport_probe_path,
)


def _evidence(verdict: str = "HOLD") -> dict:
    return {
        "P1_RUN2_RECOVERY_CLEAR": verdict,
        "run2_order_count_found": 0,
        "run2_position_count_found": 0,
        "p1_unresolved_ledger_count": 0,
        "migration_0005_present": True,
        "migration_0006_present": True,
        "recent_order_history_count": 0,
        "recent_execution_count": 0,
        "recent_closed_pnl_count": 0,
        "p1_identity_exchange_row_count": 0,
        "p1_state_counts": {},
        "p1_transition_history_count": 0,
        "error": None,
    }


def test_execute_command_response_parses_safe_metadata_only():
    result = parse_execute_command_response(
        json.dumps({"data": {"executeCommand": {"exitCode": 0, "output": "runner complete"}}})
    )
    assert result == {"remote_command_exit_code": 0, "remote_command_output_present": True}


def test_execute_command_request_uses_documented_argv_schema():
    request = build_execute_command_request(
        service_id="service-id",
        environment_id="environment-id",
        command_argv=["/bin/sh", "-lc", "export EXCHANGE_WRITE=false; python -m backend.nexus_demo_execution.p1_recovery"],
    )
    assert "$command: [String!]!" in EXECUTE_COMMAND_QUERY
    assert request["variables"]["serviceId"] == "service-id"
    assert request["variables"]["environmentId"] == "environment-id"
    assert isinstance(request["variables"]["command"], list)
    assert request["variables"]["command"][:2] == ["/bin/sh", "-lc"]
    assert "EXCHANGE_WRITE=false" in request["variables"]["command"][2]


def test_qualification_argv_requires_recovery_gate_before_go_phrase():
    command = (
        'test "${P1_RUN2_RECOVERY_CLEAR:-false}" = true && '
        "export FOUNDER_P1_APPROVED=true P1_GO=RUN_ONE_BYBIT_DEMO_TRADE"
    )
    assert command.index("P1_RUN2_RECOVERY_CLEAR") < command.index("FOUNDER_P1_APPROVED")
    assert "P1_GO=RUN_ONE_BYBIT_DEMO_TRADE" in command


@pytest.mark.parametrize("argv", [[], ["python", 1], [""]])
def test_execute_command_request_rejects_non_argv(argv):
    with pytest.raises(ValueError):
        build_execute_command_request(service_id="s", environment_id="e", command_argv=argv)  # type: ignore[arg-type]


@pytest.mark.parametrize("raw", ["", "not-json", '{"errors":[{"message":"denied"}]}', '{"data":{}}'])
def test_execute_command_response_fails_closed(raw: str):
    with pytest.raises(ValueError):
        parse_execute_command_response(raw)


def test_downloaded_recovery_evidence_accepts_complete_hold_or_pass():
    assert parse_recovery_evidence(json.dumps(_evidence("HOLD")))["P1_RUN2_RECOVERY_CLEAR"] == "HOLD"
    assert parse_recovery_evidence(json.dumps(_evidence("PASS")))["P1_RUN2_RECOVERY_CLEAR"] == "PASS"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"P1_RUN2_RECOVERY_CLEAR": "PASS"},
        {**_evidence(), "P1_RUN2_RECOVERY_CLEAR": "UNKNOWN"},
    ],
)
def test_missing_or_malformed_downloaded_evidence_fails_closed(payload: dict):
    with pytest.raises(ValueError):
        parse_recovery_evidence(json.dumps(payload))


def test_hold_evidence_cannot_qualify_recovery_gate():
    assert parse_recovery_evidence(json.dumps(_evidence("HOLD")))["P1_RUN2_RECOVERY_CLEAR"] != "PASS"


def test_pass_evidence_is_the_only_gate_value():
    assert parse_recovery_evidence(json.dumps(_evidence("PASS")))["P1_RUN2_RECOVERY_CLEAR"] == "PASS"


def test_unique_evidence_path_binds_current_run_and_attempt():
    path = unique_evidence_path(kind="p1_run2_recovery", run_id="12345", run_attempt="2")
    assert path == "/tmp/nexus_demo_validation/p1_run2_recovery_12345_2.json"
    assert "p1_run2_recovery_evidence.json" not in path
    run8 = unique_evidence_path(kind="p1_run8_accounting_recovery", run_id="12345", run_attempt="2")
    assert run8 == "/tmp/nexus_demo_validation/p1_run8_accounting_recovery_12345_2.json"
    assert "12345" in path and "2" in path


def test_unique_transport_probe_path_binds_current_run_and_attempt():
    path = unique_transport_probe_path(run_id="12345", run_attempt="2")
    assert path == "/tmp/nexus_demo_validation/p1_transport_probe_12345_2.txt"


@pytest.mark.parametrize(
    "status,downloaded,expected",
    [(200, b"", b"marker"), (200, b"wrong", b"marker"), (404, b"marker", b"marker")],
)
def test_transport_probe_rejects_empty_or_mismatched_downloads(status: int, downloaded: bytes, expected: bytes):
    assert transport_probe_matches(http_status=status, downloaded=downloaded, expected=expected) is False


def test_transport_probe_accepts_exact_nonempty_marker_only():
    assert transport_probe_matches(http_status=200, downloaded=b"P1_TRANSPORT_1_1", expected=b"P1_TRANSPORT_1_1")


@pytest.mark.parametrize("status,size", [(404, 100), (200, 0), (500, 0)])
def test_missing_or_empty_unique_evidence_fails_closed(status: int, size: int):
    assert evidence_download_ready(http_status=status, content_bytes=size) is False


def test_service_exec_transport_never_decides_recovery_pass():
    assert recovery_gate_may_pass(service_exec_exit=0, evidence_verdict=None) is False
    assert recovery_gate_may_pass(service_exec_exit=1, evidence_verdict=None) is False
    assert recovery_gate_may_pass(service_exec_exit=0, evidence_verdict="HOLD") is False
    assert recovery_gate_may_pass(service_exec_exit=1, evidence_verdict="PASS") is True


def test_runner_stdout_diagnostic_is_allowlisted_and_cannot_set_gate():
    raw = 'transport preface {"P1_RUN2_RECOVERY_CLEAR":"PASS","run2_order_count_found":2,"run2_position_count_found":1,"p1_unresolved_ledger_count":3,"error":"postgres://secret"}'
    diagnostic = parse_runner_stdout_diagnostic(raw)
    assert diagnostic == {
        "runner_json_detected": True,
        "runner_verdict": "PASS",
        "runner_error": "redacted",
        "runner_run2_order_count_found": 2,
        "runner_run2_position_count_found": 1,
        "runner_unresolved_ledger_count": 3,
    }
    assert recovery_gate_may_pass(service_exec_exit=0, evidence_verdict=None) is False


def test_non_json_stdout_is_diagnostic_hold_only():
    assert parse_runner_stdout_diagnostic("transport only") == {"runner_json_detected": False}


def test_workflows_configure_dsn_before_deploy_and_probe_the_final_runtime():
    workflows = (
        Path(".github/workflows/founder_approved_bybit_demo_p1_run2_recovery.yml"),
        Path(".github/workflows/founder_approved_bybit_demo_p1_qualification.yml"),
        Path(".github/workflows/founder_approved_bybit_demo_p1_run8_accounting_recovery.yml"),
    )
    for workflow_path in workflows:
        source = workflow_path.read_text(encoding="utf-8")
        assert source.index('set_var NEXUS_POSTGRES_URL "$NEXUS_STAGING_POSTGRES_URL"') < source.index(
            "zeabur deploy"
        )
        assert "P1_LEDGER_DSN_PRESENT=true" in source
        assert "P1_SERVICE_EXEC_FILE_CHANNEL_PASS=true" in source
        readiness_end = source.index("P1_VALIDATION_SERVICE_RUNTIME_READY=true")
        recovery_or_qualification_exec = source.index("python -m backend.nexus_demo_execution.p1_")
        between = source[readiness_end:recovery_or_qualification_exec]
        assert "zeabur variable create" not in between
        assert "zeabur variable update" not in between


def test_recovery_workflow_uses_unique_probe_and_stdout_is_diagnostic_only():
    source = Path(".github/workflows/founder_approved_bybit_demo_p1_run2_recovery.yml").read_text(encoding="utf-8")
    assert "p1_transport_probe_${GITHUB_RUN_ID}_${GITHUB_RUN_ATTEMPT}.txt" in source
    assert "P1_TRANSPORT_${GITHUB_RUN_ID}_${GITHUB_RUN_ATTEMPT}" in source
    assert "p1_parse_recovery_stdout.py" in source
    assert source.index("P1_SERVICE_EXEC_FILE_CHANNEL_PASS=true") < source.index(
        "python -m backend.nexus_demo_execution.p1_recovery"
    )
    assert source.index("p1_parse_recovery_stdout.py") < source.index("p1_parse_recovery_json.py")


def test_run8_workflow_uses_bootstrap_and_run8_parser():
    source = Path(".github/workflows/founder_approved_bybit_demo_p1_run8_accounting_recovery.yml").read_text(
        encoding="utf-8"
    )
    assert "p1_run8_accounting_recovery_bootstrap" in source
    assert "p1_parse_run8_stdout.py" in source
    assert "p1_parse_recovery_stdout.py" not in source
    assert "p1_run8_bootstrap_failure.json" in source
    assert "p1_reject_empty_json" in source
    assert "PYTHONPATH=/app" in source
    assert 'set_var NEXUS_EXPECTED_SHA "$GITHUB_SHA"' in source
    assert "COPY DEPLOYMENT_COMMIT /app/DEPLOYMENT_COMMIT" in source
    assert "COPY SOURCE_COMMIT /app/SOURCE_COMMIT" in source
    assert "p1_run8_baked_identity_probe.sh" in source
    assert "P1_RUN8_BAKED_IDENTITY_PASS=true" in Path("tools/ci/p1_run8_baked_identity_probe.sh").read_text(encoding="utf-8")


def test_recovery_module_contains_no_exchange_write_methods():
    for rel in (
        "backend/nexus_demo_execution/p1_recovery.py",
        "backend/nexus_demo_execution/p1_run8_accounting_recovery.py",
    ):
        source = Path(rel).read_text(encoding="utf-8")
        assert ".create_market_order(" not in source
        assert ".close_reduce_only(" not in source
        assert ".cancel_order(" not in source
