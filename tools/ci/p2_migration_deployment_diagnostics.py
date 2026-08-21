"""Classify Zeabur deployment get/log output for P2 migration (no secrets).

Positive RUNNING authority comes ONLY from exact normalized structured status
tokens. Raw CLI text and substring matches must never authorize service-exec.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

# Exact normalized tokens only (after uppercasing + non-alnum → underscore).
POSITIVE_RUNNING_TOKENS = frozenset({"RUNNING", "READY", "ACTIVE"})
BUILDING_TOKENS = frozenset({"BUILDING", "PENDING", "QUEUED", "WAITING"})
DEPLOYING_TOKENS = frozenset({"DEPLOYING", "STARTING", "RESTARTING"})
FAILED_TOKENS = frozenset({"FAILED", "ERROR", "BUILD_FAILED", "DEPLOY_FAILED", "DEPLOYMENT_FAILED"})
CRASHED_TOKENS = frozenset({"CRASHED", "CRASH"})
SUSPENDED_TOKENS = frozenset({"SUSPENDED", "INACTIVE", "STOPPED", "STOP"})
# Negative tokens take precedence over any positive lookalike.
NEGATIVE_TOKENS = frozenset(
    {
        "NOT_RUNNING",
        "NOTRUNNING",
        "INACTIVE",
        "SUSPENDED",
        "STOPPED",
        "FAILED",
        "CRASHED",
        "NOT_READY",
        "NOTREADY",
        "UNREADY",
        "BUILD_FAILED",
        "DEPLOY_FAILED",
        "DEPLOYMENT_FAILED",
        "ERROR",
    }
)

# Raw text may only contribute wait/fail hints — never positive RUNNING.
RAW_BUILDING_HINTS = (
    re.compile(r"\bBUILDING\b", re.I),
    re.compile(r"\bPENDING\b", re.I),
    re.compile(r"\bQUEUED\b", re.I),
)
RAW_DEPLOYING_HINTS = (
    re.compile(r"\bDEPLOYING\b", re.I),
    re.compile(r"\bSTARTING\b", re.I),
)
RAW_FAILED_HINTS = (
    re.compile(r"\bBUILD[_\s-]?FAILED\b", re.I),
    re.compile(r"\bDEPLOY(?:MENT)?[_\s-]?FAILED\b", re.I),
)
RAW_CRASH_HINTS = (
    re.compile(r"\bCRASH(?:ED)?\b", re.I),
    re.compile(r"Traceback \(most recent call last\)"),
)

# Known Zeabur CLI / control-plane signatures (not generic "ERROR" from app logs).
CLI_SEMANTIC_ERROR_PATTERNS = (
    re.compile(r"failed to get service", re.I),
    re.compile(r"either id or ownerName,\s*projectName,\s*and name must be specified", re.I),
    re.compile(r"execute command failed", re.I),
    re.compile(r"NOT_RUNNING_SERVICE", re.I),
    re.compile(r"Inactiv(?:e|ate)\s+service", re.I),
)

CONTAINER_IMAGE_BUILD_LOG_NA = re.compile(
    r"no build logs available:\s*this service was started from a container\s+"
    r"image and was not built on Zeabur",
    re.I,
)


def detect_zeabur_cli_semantic_error(*blobs: str) -> str | None:
    """Return the first matched known CLI semantic-error signature, else None."""
    for blob in blobs:
        text = blob or ""
        if not text.strip():
            continue
        # Container-image build-log absence is informational, never a CLI error.
        if CONTAINER_IMAGE_BUILD_LOG_NA.search(text):
            text = CONTAINER_IMAGE_BUILD_LOG_NA.sub(" ", text)
        for pattern in CLI_SEMANTIC_ERROR_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(0)
    return None


def detect_container_image_build_log_na(*blobs: str) -> bool:
    return any(CONTAINER_IMAGE_BUILD_LOG_NA.search(blob or "") for blob in blobs)


def sanitize_log_tail(raw: str, *, max_chars: int = 1200) -> str:
    text = (raw or "")[-max_chars:]
    text = re.sub(r"postgresql(?:\+[^:\s]+)?://\S+", "postgresql://***REDACTED***", text, flags=re.I)
    text = re.sub(r"postgres://\S+", "postgres://***REDACTED***", text, flags=re.I)
    text = re.sub(r"Bearer\s+\S+", "Bearer ***REDACTED***", text, flags=re.I)
    text = re.sub(r"ZEABUR_TOKEN=\S+", "ZEABUR_TOKEN=***REDACTED***", text, flags=re.I)
    text = re.sub(r"password[=:]\S+", "password=***REDACTED***", text, flags=re.I)
    text = re.sub(r"[A-Za-z0-9_\-+/=]{48,}", "***REDACTED***", text)
    return text


def normalize_status_token(value: str | None) -> str:
    text = (value or "").strip().upper()
    if not text:
        return ""
    text = re.sub(r"[^A-Z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def _parse_json_blob(raw: str) -> Any | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", text, re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None


def _status_strings(payload: Any) -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        for key in ("status", "state", "Status", "State", "phase", "Phase"):
            value = payload.get(key)
            if value is not None and not isinstance(value, (dict, list)):
                found.append(str(value))
            elif isinstance(value, dict):
                # env-id → status map
                for nested_val in list(value.values())[:20]:
                    if nested_val is not None and not isinstance(nested_val, (dict, list)):
                        found.append(str(nested_val))
        for nested_key in ("deployment", "data", "result", "service"):
            nested = payload.get(nested_key)
            if nested is not None:
                found.extend(_status_strings(nested))
        for item in payload.get("deployments") or payload.get("edges") or []:
            node = item if not isinstance(item, dict) else item.get("node") or item
            found.extend(_status_strings(node))
        for item in payload.get("environments") or payload.get("Environments") or []:
            found.extend(_status_strings(item))
    elif isinstance(payload, list):
        for item in payload[:5]:
            found.extend(_status_strings(item))
    return found


def _status_paths_found(payload: Any, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if key in {"status", "state", "Status", "State", "phase", "Phase"}:
                paths.append(path)
            if isinstance(value, (dict, list)) and len(paths) < 40:
                paths.extend(_status_paths_found(value, path))
    elif isinstance(payload, list):
        for idx, item in enumerate(payload[:5]):
            paths.extend(_status_paths_found(item, f"{prefix}[{idx}]"))
    return paths[:40]


def json_shape_metadata(raw: str, payload: Any | None) -> dict[str, Any]:
    text = (raw or "").strip()
    if payload is None:
        return {
            "json_type": "none" if not text else "unparsed",
            "top_level_keys": [],
            "status_paths_found": [],
        }
    if isinstance(payload, dict):
        return {
            "json_type": "object",
            "top_level_keys": sorted(str(k) for k in payload.keys())[:40],
            "status_paths_found": _status_paths_found(payload),
        }
    if isinstance(payload, list):
        return {
            "json_type": "array",
            "top_level_keys": [f"len={len(payload)}"],
            "status_paths_found": _status_paths_found(payload),
        }
    return {
        "json_type": type(payload).__name__,
        "top_level_keys": [],
        "status_paths_found": [],
    }


def _state_from_tokens(tokens: list[str]) -> str:
    negative_hit = next((token for token in tokens if token in NEGATIVE_TOKENS), "")
    positive_hit = next((token for token in tokens if token in POSITIVE_RUNNING_TOKENS), "")
    building_hit = next((token for token in tokens if token in BUILDING_TOKENS), "")
    deploying_hit = next((token for token in tokens if token in DEPLOYING_TOKENS), "")
    failed_hit = next((token for token in tokens if token in FAILED_TOKENS), "")
    crashed_hit = next((token for token in tokens if token in CRASHED_TOKENS), "")
    suspended_hit = next((token for token in tokens if token in SUSPENDED_TOKENS), "")
    if negative_hit in {"FAILED", "BUILD_FAILED", "DEPLOY_FAILED", "DEPLOYMENT_FAILED", "ERROR", "CRASHED"} or failed_hit or crashed_hit:
        return "RUNNING_THEN_CRASHED" if crashed_hit or negative_hit == "CRASHED" else "FAILED"
    if negative_hit in {"SUSPENDED", "INACTIVE", "STOPPED"} or suspended_hit:
        return "SUSPENDED"
    if negative_hit in {"NOT_RUNNING", "NOTRUNNING", "NOT_READY", "NOTREADY", "UNREADY"}:
        return "NOT_RUNNING"
    if positive_hit:
        return "RUNNING"
    if building_hit:
        return "BUILDING"
    if deploying_hit:
        return "DEPLOYING"
    return "UNKNOWN"


def _raw_hint_state(build_text: str, runtime_text: str, combined_text: str) -> str | None:
    """Raw unstructured text may hint BUILDING/DEPLOYING/FAILED/CRASHED only."""
    # Strip informational container-image NA so it cannot drive BUILDING/FAILED.
    build_text = CONTAINER_IMAGE_BUILD_LOG_NA.sub(" ", build_text or "")
    combined_text = CONTAINER_IMAGE_BUILD_LOG_NA.sub(" ", combined_text or "")
    if any(pat.search(runtime_text) for pat in RAW_CRASH_HINTS):
        return "RUNNING_THEN_CRASHED"
    if any(pat.search(build_text) or pat.search(combined_text) for pat in RAW_FAILED_HINTS):
        return "FAILED"
    if any(pat.search(combined_text) or pat.search(build_text) for pat in RAW_BUILDING_HINTS):
        return "BUILDING"
    if any(pat.search(combined_text) or pat.search(runtime_text) for pat in RAW_DEPLOYING_HINTS):
        return "DEPLOYING"
    return None


def classify_deployment_snapshot(
    *,
    deployment_get_raw: str = "",
    deployment_list_raw: str = "",
    build_log_raw: str = "",
    runtime_log_raw: str = "",
    service_get_raw: str = "",
    deployment_get_exit: int | None = None,
    deployment_list_exit: int | None = None,
    build_log_exit: int | None = None,
    runtime_log_exit: int | None = None,
    service_get_exit: int | None = None,
) -> dict[str, Any]:
    get_exit = 0 if deployment_get_exit is None else int(deployment_get_exit)
    list_exit = 0 if deployment_list_exit is None else int(deployment_list_exit)
    build_exit = 0 if build_log_exit is None else int(build_log_exit)
    runtime_exit = 0 if runtime_log_exit is None else int(runtime_log_exit)
    svc_exit = 0 if service_get_exit is None else int(service_get_exit)

    container_image_service = detect_container_image_build_log_na(build_log_raw, runtime_log_raw)

    # Semantic CLI failures are authoritative even when process exit is 0.
    semantic_match = detect_zeabur_cli_semantic_error(
        deployment_get_raw,
        build_log_raw,
        runtime_log_raw,
        deployment_list_raw,
        service_get_raw,
    )
    semantic_cli_error = semantic_match is not None

    get_payload = None
    list_payload = None
    service_payload = None
    if not semantic_cli_error:
        get_payload = _parse_json_blob(deployment_get_raw) if get_exit == 0 else None
        list_payload = _parse_json_blob(deployment_list_raw) if list_exit == 0 else None
        service_payload = _parse_json_blob(service_get_raw) if svc_exit == 0 else None

    deploy_statuses = _status_strings(get_payload) + _status_strings(list_payload)
    deploy_tokens = [normalize_status_token(item) for item in deploy_statuses]
    deploy_tokens = [token for token in deploy_tokens if token]
    service_statuses = _status_strings(service_payload)
    service_tokens = [normalize_status_token(item) for item in service_statuses]
    service_tokens = [token for token in service_tokens if token]

    build_text = build_log_raw or ""
    runtime_text = runtime_log_raw or ""
    # Deployment raw hints must not use service JSON text (service is structured-only).
    deploy_combined_text = "\n".join(
        [
            deployment_get_raw or "",
            deployment_list_raw or "",
            build_text,
            runtime_text,
        ]
    )

    exit_failed = any(code != 0 for code in (get_exit, list_exit, build_exit, runtime_exit, svc_exit))
    cli_failed = exit_failed or semantic_cli_error

    deployment_state = _state_from_tokens(deploy_tokens)
    if semantic_cli_error:
        deployment_state = "CLI_ERROR"
    elif not deploy_tokens:
        # Empty structured deployment: do not invent RUNNING; raw may only wait/fail.
        raw_state = _raw_hint_state(build_text, runtime_text, deploy_combined_text)
        if raw_state in {"FAILED", "RUNNING_THEN_CRASHED", "BUILDING", "DEPLOYING"}:
            deployment_state = raw_state
        elif (
            not (deployment_get_raw or "").strip()
            and not (deployment_list_raw or "").strip()
            and not (service_get_raw or "").strip()
            and get_exit == 0
            and list_exit == 0
            and not semantic_cli_error
        ):
            # Truly empty initial evidence before any probe output — still provisioning.
            deployment_state = "BUILDING"
        else:
            deployment_state = "UNKNOWN"
    elif deployment_state == "RUNNING" and (get_exit != 0 or get_payload is None or semantic_cli_error):
        deployment_state = "UNKNOWN"

    service_state = _state_from_tokens(service_tokens)
    if svc_exit != 0 or semantic_cli_error:
        service_state = "UNKNOWN" if not semantic_cli_error else "CLI_ERROR"
    elif service_payload is None and bool((service_get_raw or "").strip()):
        # Malformed JSON containing "RUNNING" must never authorize.
        service_state = "UNKNOWN"
    elif not service_tokens and not (service_get_raw or "").strip() and svc_exit == 0:
        service_state = "UNKNOWN"
    elif service_state == "RUNNING" and (svc_exit != 0 or service_payload is None):
        service_state = "UNKNOWN"

    service_status_token = next(
        (token for token in service_tokens if token in POSITIVE_RUNNING_TOKENS | NEGATIVE_TOKENS | BUILDING_TOKENS | DEPLOYING_TOKENS | FAILED_TOKENS | SUSPENDED_TOKENS),
        (service_tokens[0] if service_tokens else ""),
    )

    # Explicit metadata negatives are vetoes. UNKNOWN / empty never authorize RUNNING
    # and must not permanently block operational service-exec readiness.
    METADATA_VETO_STATES = frozenset(
        {
            "FAILED",
            "RUNNING_THEN_CRASHED",
            "SUSPENDED",
            "CLI_ERROR",
        }
    )
    # Structured INACTIVE/STOPPED map to SUSPENDED via _state_from_tokens.
    deployment_veto = deployment_state in METADATA_VETO_STATES
    service_veto = service_state in METADATA_VETO_STATES
    # NOT_RUNNING metadata is not a hard veto — operational probe waits on NOT_RUNNING_SERVICE.
    deployment_waits = deployment_state in {"BUILDING", "DEPLOYING"}
    service_waits = service_state in {"BUILDING", "DEPLOYING"}

    metadata_veto = bool(semantic_cli_error or deployment_veto or service_veto)
    wait_for_deployment = bool((deployment_waits or service_waits) and not metadata_veto)
    # Metadata must never authorize migration service-exec; operational probe is authoritative.
    service_authority = False
    service_exec_allowed = False
    proceed_to_operational_probe = (not metadata_veto) and (not wait_for_deployment)

    if semantic_cli_error:
        gate_state = "CLI_ERROR"
    elif deployment_veto:
        gate_state = deployment_state
    elif service_veto:
        gate_state = service_state
    elif wait_for_deployment:
        gate_state = deployment_state if deployment_waits else service_state
    else:
        # Preserve UNKNOWN / RUNNING metadata as diagnostic only — do not promote to PASS.
        gate_state = deployment_state if deployment_state != "UNKNOWN" else service_state

    fail_closed = metadata_veto

    deploy_meta = json_shape_metadata(deployment_get_raw, get_payload)
    service_meta = json_shape_metadata(service_get_raw, service_payload)

    return {
        "P2_MIGRATION_DEPLOYMENT_STATUS": deployment_state,
        "P2_MIGRATION_SERVICE_STATUS": service_status_token or service_state,
        "P2_MIGRATION_SERVICE_STATUS_AUTHORITY": service_authority,
        "P2_MIGRATION_CONTAINER_IMAGE_SERVICE": container_image_service,
        "P2_MIGRATION_BUILD_LOG_NOT_APPLICABLE": container_image_service,
        "P2_MIGRATION_BUILD_STATUS": "FAILED"
        if gate_state in {"FAILED", "RUNNING_THEN_CRASHED", "CLI_ERROR"}
        else (
            "NOT_APPLICABLE"
            if container_image_service and gate_state in {"UNKNOWN", "RUNNING", "BUILDING", "DEPLOYING"}
            else ("BUILDING" if gate_state == "BUILDING" else ("READY" if gate_state == "RUNNING" else gate_state))
        ),
        "P2_MIGRATION_RUNTIME_STATUS": "CRASHED"
        if gate_state == "RUNNING_THEN_CRASHED"
        else (
            "RUNNING"
            if gate_state == "RUNNING"
            else ("NOT_RUNNING" if gate_state not in {"UNKNOWN", "BUILDING", "DEPLOYING"} else gate_state)
        ),
        "P2_MIGRATION_BUILD_LOG_TAIL": sanitize_log_tail(build_log_raw),
        "P2_MIGRATION_RUNTIME_LOG_TAIL": sanitize_log_tail(runtime_log_raw),
        "structured_status_tokens": deploy_tokens,
        "service_structured_status_tokens": service_tokens,
        "deployment_get_exit": get_exit,
        "deployment_list_exit": list_exit,
        "build_log_exit": build_exit,
        "runtime_log_exit": runtime_exit,
        "service_get_exit": svc_exit,
        "deployment_get_json_type": deploy_meta["json_type"],
        "deployment_get_top_level_keys": deploy_meta["top_level_keys"],
        "deployment_get_status_paths_found": deploy_meta["status_paths_found"],
        "service_get_json_type": service_meta["json_type"],
        "service_get_top_level_keys": service_meta["top_level_keys"],
        "service_get_status_paths_found": service_meta["status_paths_found"],
        "cli_command_failed": cli_failed,
        "cli_semantic_error": semantic_cli_error,
        "cli_semantic_error_match": semantic_match or "",
        "metadata_veto": metadata_veto,
        "proceed_to_operational_probe": proceed_to_operational_probe,
        "service_exec_allowed": service_exec_allowed,
        "wait_for_deployment": wait_for_deployment,
        "fail_closed": fail_closed,
        "gate_status": gate_state,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def wait_for_deployment_running(
    *,
    probe: Callable[[int], dict[str, Any]],
    max_attempts: int = 24,
    interval_sec: float = 10.0,
    sleep: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Poll deployment/service diagnostics until exec allowed, or fail closed.

    Does not perform service exec. BUILDING/DEPLOYING continue waiting.
    """
    sleeper = sleep or (lambda _seconds: None)
    history: list[dict[str, Any]] = []
    last: dict[str, Any] = {}
    for attempt in range(1, max_attempts + 1):
        raw = probe(attempt)
        classified = classify_deployment_snapshot(
            deployment_get_raw=str(raw.get("deployment_get") or ""),
            deployment_list_raw=str(raw.get("deployment_list") or ""),
            build_log_raw=str(raw.get("build_log") or ""),
            runtime_log_raw=str(raw.get("runtime_log") or ""),
            service_get_raw=str(raw.get("service_get") or ""),
            deployment_get_exit=raw.get("deployment_get_exit"),  # type: ignore[arg-type]
            deployment_list_exit=raw.get("deployment_list_exit"),  # type: ignore[arg-type]
            build_log_exit=raw.get("build_log_exit"),  # type: ignore[arg-type]
            runtime_log_exit=raw.get("runtime_log_exit"),  # type: ignore[arg-type]
            service_get_exit=raw.get("service_get_exit"),  # type: ignore[arg-type]
        )
        row = {"attempt": attempt, **classified}
        history.append(row)
        last = classified
        if classified.get("proceed_to_operational_probe"):
            return {
                "ready_for_service_exec": False,
                "proceed_to_operational_probe": True,
                "attempts": attempt,
                "history": history,
                **classified,
            }
        if classified["wait_for_deployment"]:
            sleeper(interval_sec)
            continue
        return {
            "ready_for_service_exec": False,
            "proceed_to_operational_probe": False,
            "attempts": attempt,
            "history": history,
            **classified,
        }
    return {
        "ready_for_service_exec": False,
        "attempts": max_attempts,
        "history": history,
        **last,
        "P2_MIGRATION_DEPLOYMENT_STATUS": last.get("P2_MIGRATION_DEPLOYMENT_STATUS") or "UNKNOWN",
        "fail_closed": True,
        "timeout": True,
    }


def _help_has_flag(help_text: str, flag: str) -> bool:
    """True only when the exact CLI flag appears in this help blob."""
    needle = flag if flag.startswith("--") else f"--{flag}"
    return needle.lower() in (help_text or "").lower()


def parse_zeabur_deployment_help(
    *,
    get_help: str = "",
    log_help: str = "",
    list_help: str = "",
    get_help_exit: int = 0,
    log_help_exit: int = 0,
    list_help_exit: int | None = None,
    parent_help: str = "",
) -> dict[str, Any]:
    """Parse get/log/list subcommand help independently.

    Parent ``deployment --help`` must never authorize a selector: it may list
    subcommand names without exposing ``--service-name`` / ``--service-id``.
    """
    _ = parent_help  # intentionally ignored for selector capability
    get_ok = int(get_help_exit) == 0
    log_ok = int(log_help_exit) == 0
    list_exit = 0 if list_help_exit is None else int(list_help_exit)
    list_ok = list_exit == 0 and bool((list_help or "").strip())

    get_supports_service_name = get_ok and _help_has_flag(get_help, "--service-name")
    log_supports_service_name = log_ok and _help_has_flag(log_help, "--service-name")
    list_supports_service_name = list_ok and _help_has_flag(list_help, "--service-name")
    get_supports_service_id = get_ok and _help_has_flag(get_help, "--service-id")
    log_supports_service_id = log_ok and _help_has_flag(log_help, "--service-id")
    list_supports_service_id = list_ok and _help_has_flag(list_help, "--service-id")
    get_supports_env_id = get_ok and _help_has_flag(get_help, "--env-id")
    log_supports_env_id = log_ok and _help_has_flag(log_help, "--env-id")

    # Migration diagnostics: SERVICE_ID only. Never select service-name / owner / project.
    if (
        get_supports_service_id
        and log_supports_service_id
        and get_supports_env_id
        and log_supports_env_id
    ):
        preferred = "service-id"
    else:
        preferred = "none"

    supports_deployment_list = (
        preferred == "service-id"
        and list_supports_service_id
        and _help_has_flag(list_help, "--env-id")
    )

    return {
        "get_help_exit": int(get_help_exit),
        "log_help_exit": int(log_help_exit),
        "list_help_exit": list_exit,
        "get_supports_service_name": get_supports_service_name,
        "log_supports_service_name": log_supports_service_name,
        "list_supports_service_name": list_supports_service_name,
        "get_supports_service_id": get_supports_service_id,
        "log_supports_service_id": log_supports_service_id,
        "list_supports_service_id": list_supports_service_id,
        "get_supports_env_id": get_supports_env_id,
        "log_supports_env_id": log_supports_env_id,
        "supports_service_name": False,
        "supports_service_id": get_supports_service_id and log_supports_service_id,
        "supports_deployment_list": supports_deployment_list,
        "preferred_selector": preferred,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment-get", default="")
    parser.add_argument("--deployment-list", default="")
    parser.add_argument("--build-log", default="")
    parser.add_argument("--runtime-log", default="")
    parser.add_argument("--service-get", default="")
    parser.add_argument("--deployment-get-exit", type=int, default=0)
    parser.add_argument("--deployment-list-exit", type=int, default=0)
    parser.add_argument("--build-log-exit", type=int, default=0)
    parser.add_argument("--runtime-log-exit", type=int, default=0)
    parser.add_argument("--service-get-exit", type=int, default=0)
    parser.add_argument("--emit-env", action="store_true")
    parser.add_argument("--write-artifact", default="")
    parser.add_argument("--parse-get-help-file", default="")
    parser.add_argument("--parse-log-help-file", default="")
    parser.add_argument("--parse-list-help-file", default="")
    parser.add_argument("--get-help-exit", type=int, default=0)
    parser.add_argument("--log-help-exit", type=int, default=0)
    parser.add_argument("--list-help-exit", type=int, default=0)
    parser.add_argument(
        "--parse-help-file",
        default="",
        help="Deprecated parent-help path; ignored for selector (kept for fail-closed diagnostics).",
    )
    args = parser.parse_args(argv)

    def _read(path: str) -> str:
        if not path:
            return ""
        return Path(path).read_text(encoding="utf-8", errors="replace")

    if args.parse_get_help_file or args.parse_log_help_file or args.parse_list_help_file or args.parse_help_file:
        parsed = parse_zeabur_deployment_help(
            get_help=_read(args.parse_get_help_file),
            log_help=_read(args.parse_log_help_file),
            list_help=_read(args.parse_list_help_file),
            get_help_exit=args.get_help_exit,
            log_help_exit=args.log_help_exit,
            list_help_exit=args.list_help_exit,
            parent_help=_read(args.parse_help_file),
        )
        # Always emit JSON (exit 0). Workflow evaluates preferred_selector explicitly.
        print(json.dumps(parsed, sort_keys=True))
        return 0

    classified = classify_deployment_snapshot(
        deployment_get_raw=_read(args.deployment_get),
        deployment_list_raw=_read(args.deployment_list),
        build_log_raw=_read(args.build_log),
        runtime_log_raw=_read(args.runtime_log),
        service_get_raw=_read(args.service_get),
        deployment_get_exit=args.deployment_get_exit,
        deployment_list_exit=args.deployment_list_exit,
        build_log_exit=args.build_log_exit,
        runtime_log_exit=args.runtime_log_exit,
        service_get_exit=args.service_get_exit,
    )
    print(json.dumps(classified, sort_keys=True))
    if args.emit_env:
        for key in (
            "P2_MIGRATION_DEPLOYMENT_STATUS",
            "P2_MIGRATION_SERVICE_STATUS",
            "P2_MIGRATION_BUILD_STATUS",
            "P2_MIGRATION_RUNTIME_STATUS",
        ):
            print(f"{key}={classified[key]}")
        print(f"P2_MIGRATION_SERVICE_STATUS_AUTHORITY={str(classified['P2_MIGRATION_SERVICE_STATUS_AUTHORITY']).lower()}")
        print(f"P2_MIGRATION_CONTAINER_IMAGE_SERVICE={str(classified['P2_MIGRATION_CONTAINER_IMAGE_SERVICE']).lower()}")
        print(f"P2_MIGRATION_BUILD_LOG_NOT_APPLICABLE={str(classified['P2_MIGRATION_BUILD_LOG_NOT_APPLICABLE']).lower()}")
        print(f"deployment_get_exit={classified['deployment_get_exit']}")
        print(f"deployment_list_exit={classified['deployment_list_exit']}")
        print(f"build_log_exit={classified['build_log_exit']}")
        print(f"runtime_log_exit={classified['runtime_log_exit']}")
        print(f"service_get_exit={classified['service_get_exit']}")
        print("P2_MIGRATION_BUILD_LOG_TAIL=<<BEGIN")
        print(classified.get("P2_MIGRATION_BUILD_LOG_TAIL") or "")
        print("P2_MIGRATION_BUILD_LOG_TAIL=<<END")
        print("P2_MIGRATION_RUNTIME_LOG_TAIL=<<BEGIN")
        print(classified.get("P2_MIGRATION_RUNTIME_LOG_TAIL") or "")
        print("P2_MIGRATION_RUNTIME_LOG_TAIL=<<END")
        print(f"metadata_veto={str(classified['metadata_veto']).lower()}")
        print(f"proceed_to_operational_probe={str(classified['proceed_to_operational_probe']).lower()}")
        print(f"service_exec_allowed={str(classified['service_exec_allowed']).lower()}")
        print(f"wait_for_deployment={str(classified['wait_for_deployment']).lower()}")
        print(f"fail_closed={str(classified['fail_closed']).lower()}")
        print(f"cli_command_failed={str(classified['cli_command_failed']).lower()}")
        print(f"cli_semantic_error={str(classified['cli_semantic_error']).lower()}")
    if args.write_artifact:
        out = Path(args.write_artifact)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(classified, indent=2), encoding="utf-8")
    # Exit 0 = proceed to operational probe (metadata did not veto). Never means migration-ready.
    if classified.get("proceed_to_operational_probe"):
        return 0
    if classified["wait_for_deployment"]:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
