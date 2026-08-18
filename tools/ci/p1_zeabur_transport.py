"""Pure parsers for the documented Zeabur executeCommand/file transport."""
from __future__ import annotations

import json
from typing import Any

EXECUTE_COMMAND_QUERY = (
    "mutation ExecuteCommand($serviceId: ObjectID!, $environmentId: ObjectID!, "
    "$command: [String!]!) { executeCommand(serviceID: $serviceId, "
    "environmentID: $environmentId, command: $command) { exitCode output } }"
)


def unique_evidence_path(*, kind: str, run_id: str, run_attempt: str) -> str:
    if kind not in {"p1_run2_recovery", "p1_qualification", "p1_run8_accounting_recovery"}:
        raise ValueError("evidence_kind_invalid")
    if not run_id or not run_attempt or not run_id.isdigit() or not run_attempt.isdigit():
        raise ValueError("evidence_run_identity_invalid")
    return f"/tmp/nexus_demo_validation/{kind}_{run_id}_{run_attempt}.json"


def unique_transport_probe_path(*, run_id: str, run_attempt: str) -> str:
    if not run_id or not run_attempt or not run_id.isdigit() or not run_attempt.isdigit():
        raise ValueError("transport_probe_run_identity_invalid")
    return f"/tmp/nexus_demo_validation/p1_transport_probe_{run_id}_{run_attempt}.txt"


def evidence_download_ready(*, http_status: int, content_bytes: int) -> bool:
    return http_status == 200 and content_bytes > 0


def transport_probe_matches(*, http_status: int, downloaded: bytes, expected: bytes) -> bool:
    return http_status == 200 and bool(downloaded) and downloaded == expected


def recovery_gate_may_pass(*, service_exec_exit: int, evidence_verdict: str | None) -> bool:
    """Evidence, never trigger transport, decides the recovery gate."""
    del service_exec_exit
    return evidence_verdict == "PASS"


def parse_runner_stdout_diagnostic(raw: str) -> dict[str, Any]:
    """Extract a tightly allowlisted diagnostic; never make a control decision."""
    decoder = json.JSONDecoder()
    payload: dict[str, Any] | None = None
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            payload = candidate
    if payload is None:
        return {"runner_json_detected": False}

    error = str(payload.get("error") or "").replace("\n", " ")[:160]
    if any(marker in error.lower() for marker in ("postgres", "password", "secret", "api_key", "token")):
        error = "redacted"
    return {
        "runner_json_detected": True,
        "runner_verdict": str(payload.get("P1_RUN2_RECOVERY_CLEAR") or "UNKNOWN"),
        "runner_error": error or None,
        "runner_run2_order_count_found": payload.get("run2_order_count_found"),
        "runner_run2_position_count_found": payload.get("run2_position_count_found"),
        "runner_unresolved_ledger_count": payload.get("p1_unresolved_ledger_count"),
    }


def build_execute_command_request(
    *, service_id: str, environment_id: str, command_argv: list[str]
) -> dict[str, Any]:
    if not service_id or not environment_id:
        raise ValueError("execute_request_identity_missing")
    if not command_argv or any(not isinstance(item, str) or not item for item in command_argv):
        raise ValueError("execute_request_command_not_argv")
    return {
        "query": EXECUTE_COMMAND_QUERY,
        "variables": {
            "serviceId": service_id,
            "environmentId": environment_id,
            "command": list(command_argv),
        },
    }


def parse_execute_command_response(raw: str) -> dict[str, Any]:
    """Return only safe execution metadata; reject GraphQL/API error envelopes."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("execute_response_malformed") from exc
    if not isinstance(payload, dict):
        raise ValueError("execute_response_not_object")
    if payload.get("errors"):
        first = (payload["errors"] or [{}])[0] or {}
        message = str(first.get("message") or "unknown").replace("\n", " ")[:160]
        raise ValueError(f"execute_response_graphql_error:{message}")
    command = ((payload.get("data") or {}).get("executeCommand") or {})
    if not isinstance(command, dict) or "exitCode" not in command:
        raise ValueError("execute_response_missing_result")
    output = command.get("output")
    return {
        "remote_command_exit_code": command.get("exitCode"),
        "remote_command_output_present": bool(str(output or "").strip()),
    }


RUN8_COMMON_FIELDS = (
    "BYBIT_DEMO_SINGLE_TRADE_E2E_PASS",
    "AUTONOMOUS_BYBIT_DEMO_ARM_READY",
    "recovery_stage",
    "candidate_count",
    "create_order_calls",
    "exchange_write_call_count",
)
RUN8_RECOVERY_FIELDS = RUN8_COMMON_FIELDS + (
    "P1_ENTRY_RECONCILIATION_PASS",
    "P1_CLOSE_RECONCILIATION_PASS",
    "P1_EXCHANGE_REALIZED_PNL_PASS",
    "P1_DURABLE_LEDGER_LIFECYCLE_PASS",
    "P1_RUN8_POSITION_FLAT",
    "P1_RUN8_EXACT_CLOSED_PNL_MATCH",
    "P1_RUN8_LEDGER_FINALIZED",
    "entry_read_pass",
    "close_read_pass",
    "position_flat",
    "execution_identity_pass",
    "closed_pnl_exact_match",
    "ledger_finalization_pass",
    "error",
)
RUN8_BOOTSTRAP_FIELDS = (
    "BYBIT_DEMO_SINGLE_TRADE_E2E_PASS",
    "AUTONOMOUS_BYBIT_DEMO_ARM_READY",
    "recovery_stage",
    "exception_type",
    "create_order_calls",
    "exchange_write_call_count",
)
RUN2_ONLY_FIELDS = (
    "P1_RUN2_RECOVERY_CLEAR",
    "run2_order_count_found",
    "run2_position_count_found",
    "p1_unresolved_ledger_count",
)


def _load_json_object(raw: str, *, kind: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{kind}_malformed") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{kind}_not_object")
    return payload


def parse_run8_accounting_recovery_evidence(raw: str) -> dict[str, Any]:
    """Validate Run #8 recovery JSON. Never accept the Run #2 recovery schema."""
    payload = _load_json_object(raw, kind="run8_recovery_evidence")
    if any(key in payload for key in RUN2_ONLY_FIELDS):
        raise ValueError("run8_recovery_evidence_run2_schema")
    missing = [key for key in RUN8_RECOVERY_FIELDS if key not in payload]
    if missing:
        raise ValueError(f"run8_recovery_evidence_missing:{','.join(missing)}")
    if payload.get("BYBIT_DEMO_SINGLE_TRADE_E2E_PASS") not in {"PASS", "HOLD"}:
        raise ValueError("run8_recovery_evidence_invalid_verdict")
    if payload.get("AUTONOMOUS_BYBIT_DEMO_ARM_READY") != "HOLD":
        raise ValueError("run8_recovery_evidence_arm_not_hold")
    if int(payload.get("create_order_calls") or 0) != 0:
        raise ValueError("run8_recovery_evidence_create_order_nonzero")
    if int(payload.get("exchange_write_call_count") or 0) != 0:
        raise ValueError("run8_recovery_evidence_exchange_write_nonzero")
    return payload


def parse_run8_bootstrap_failure_evidence(raw: str) -> dict[str, Any]:
    """Diagnostic-only bootstrap schema. Can never PASS P1."""
    payload = _load_json_object(raw, kind="run8_bootstrap_evidence")
    if any(key in payload for key in RUN2_ONLY_FIELDS):
        raise ValueError("run8_bootstrap_evidence_run2_schema")
    missing = [key for key in RUN8_BOOTSTRAP_FIELDS if key not in payload]
    if missing:
        raise ValueError(f"run8_bootstrap_evidence_missing:{','.join(missing)}")
    if payload.get("BYBIT_DEMO_SINGLE_TRADE_E2E_PASS") != "HOLD":
        raise ValueError("run8_bootstrap_evidence_cannot_pass")
    if payload.get("AUTONOMOUS_BYBIT_DEMO_ARM_READY") != "HOLD":
        raise ValueError("run8_bootstrap_evidence_arm_not_hold")
    if int(payload.get("create_order_calls") or 0) != 0:
        raise ValueError("run8_bootstrap_evidence_create_order_nonzero")
    if int(payload.get("exchange_write_call_count") or 0) != 0:
        raise ValueError("run8_bootstrap_evidence_exchange_write_nonzero")
    if not str(payload.get("recovery_stage") or "").strip():
        raise ValueError("run8_bootstrap_evidence_stage_missing")
    if not str(payload.get("exception_type") or "").strip():
        raise ValueError("run8_bootstrap_evidence_exception_missing")
    return payload


def parse_recovery_evidence(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("recovery_evidence_malformed") from exc
    if not isinstance(payload, dict):
        raise ValueError("recovery_evidence_not_object")
    required = (
        "P1_RUN2_RECOVERY_CLEAR",
        "run2_order_count_found",
        "run2_position_count_found",
        "p1_unresolved_ledger_count",
        "migration_0005_present",
        "migration_0006_present",
        "recent_order_history_count",
        "recent_execution_count",
        "recent_closed_pnl_count",
        "p1_identity_exchange_row_count",
        "p1_state_counts",
        "p1_transition_history_count",
        "error",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"recovery_evidence_missing:{','.join(missing)}")
    if payload.get("P1_RUN2_RECOVERY_CLEAR") not in {"PASS", "HOLD"}:
        raise ValueError("recovery_evidence_invalid_verdict")
    return payload
