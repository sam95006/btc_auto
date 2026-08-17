"""Pure parsers for the documented Zeabur executeCommand/file transport."""
from __future__ import annotations

import json
from typing import Any

EXECUTE_COMMAND_QUERY = (
    "mutation ExecuteCommand($serviceId: ObjectID!, $environmentId: ObjectID!, "
    "$command: [String!]!) { executeCommand(serviceID: $serviceId, "
    "environmentID: $environmentId, command: $command) { exitCode output } }"
)


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
    if not isinstance(payload, dict) or payload.get("errors"):
        raise ValueError("execute_response_error")
    command = ((payload.get("data") or {}).get("executeCommand") or {})
    if not isinstance(command, dict) or "exitCode" not in command:
        raise ValueError("execute_response_missing_result")
    output = command.get("output")
    return {
        "remote_command_exit_code": command.get("exitCode"),
        "remote_command_output_present": bool(str(output or "").strip()),
    }


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
