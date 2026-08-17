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
    recovery_gate_may_pass,
    unique_evidence_path,
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
    assert "12345" in path and "2" in path


@pytest.mark.parametrize("status,size", [(404, 100), (200, 0), (500, 0)])
def test_missing_or_empty_unique_evidence_fails_closed(status: int, size: int):
    assert evidence_download_ready(http_status=status, content_bytes=size) is False


def test_service_exec_transport_never_decides_recovery_pass():
    assert recovery_gate_may_pass(service_exec_exit=0, evidence_verdict=None) is False
    assert recovery_gate_may_pass(service_exec_exit=1, evidence_verdict=None) is False
    assert recovery_gate_may_pass(service_exec_exit=0, evidence_verdict="HOLD") is False
    assert recovery_gate_may_pass(service_exec_exit=1, evidence_verdict="PASS") is True


def test_recovery_module_contains_no_exchange_write_methods():
    source = Path("backend/nexus_demo_execution/p1_recovery.py").read_text(encoding="utf-8")
    assert ".create_market_order(" not in source
    assert ".close_reduce_only(" not in source
    assert ".cancel_order(" not in source
