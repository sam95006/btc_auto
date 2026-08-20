"""Classify Zeabur deployment get/log output for P2 migration (no secrets)."""
from __future__ import annotations

import json
import re
from typing import Any, Callable

BUILDING_MARKERS = (
    "BUILDING",
    "building",
    "PENDING",
    "QUEUED",
    "WAITING",
)
DEPLOYING_MARKERS = (
    "DEPLOYING",
    "deploying",
    "STARTING",
    "RESTARTING",
)
RUNNING_MARKERS = (
    "RUNNING",
    "running",
    "READY",
    "ready",
    "ACTIVE",
    "active",
)
FAILED_MARKERS = (
    "FAILED",
    "failed",
    "ERROR",
    "CRASHED",
    "crash",
    "BUILD_FAILED",
)
SUSPENDED_MARKERS = (
    "SUSPENDED",
    "INACTIVE",
    "Stopped",
    "STOPPED",
)

SECRET_RE = re.compile(
    r"(postgresql(?:\+[^:]+)?://\S+|postgres://\S+|Bearer\s+\S+|ZEABUR_TOKEN=\S+|password[=:]\S+)",
    re.I,
)


def sanitize_log_tail(raw: str, *, max_chars: int = 1200) -> str:
    text = (raw or "")[-max_chars:]
    text = re.sub(r"postgresql(?:\+[^:\s]+)?://\S+", "postgresql://***REDACTED***", text, flags=re.I)
    text = re.sub(r"postgres://\S+", "postgres://***REDACTED***", text, flags=re.I)
    text = re.sub(r"Bearer\s+\S+", "Bearer ***REDACTED***", text, flags=re.I)
    text = re.sub(r"ZEABUR_TOKEN=\S+", "ZEABUR_TOKEN=***REDACTED***", text, flags=re.I)
    text = re.sub(r"password[=:]\S+", "password=***REDACTED***", text, flags=re.I)
    text = re.sub(r"[A-Za-z0-9_\-+/=]{48,}", "***REDACTED***", text)
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
            if value is not None:
                found.append(str(value))
        for nested_key in ("deployment", "data", "result", "service"):
            nested = payload.get(nested_key)
            if nested is not None:
                found.extend(_status_strings(nested))
        for item in payload.get("deployments") or payload.get("edges") or []:
            found.extend(_status_strings(item if not isinstance(item, dict) else item.get("node") or item))
    elif isinstance(payload, list):
        for item in payload[:5]:
            found.extend(_status_strings(item))
    return found


def classify_deployment_snapshot(
    *,
    deployment_get_raw: str = "",
    deployment_list_raw: str = "",
    build_log_raw: str = "",
    runtime_log_raw: str = "",
) -> dict[str, Any]:
    get_payload = _parse_json_blob(deployment_get_raw)
    list_payload = _parse_json_blob(deployment_list_raw)
    statuses = _status_strings(get_payload) + _status_strings(list_payload)
    structured = " ".join(statuses).upper()
    build_text = build_log_raw or ""
    runtime_text = runtime_log_raw or ""
    combined_upper = ((deployment_get_raw or "") + "\n" + (deployment_list_raw or "")).upper()

    def _has_any(haystack: str, markers: tuple[str, ...]) -> bool:
        upper = haystack.upper()
        return any(marker.upper() in upper for marker in markers)

    failed = False
    if _has_any(structured, ("FAILED", "BUILD_FAILED", "CRASHED")):
        failed = True
    if re.search(r"\bBUILD[_\s-]?FAILED\b", build_text, re.I):
        failed = True
    if re.search(r"\bDEPLOY(?:MENT)?[_\s-]?FAILED\b", combined_upper):
        failed = True

    crashed = bool(
        re.search(r"\bCRASH(?:ED)?\b", runtime_text, re.I)
        or "Traceback (most recent call last)" in runtime_text
        or "RUNNING_THEN_CRASHED" in structured
    )
    building = _has_any(structured or combined_upper, BUILDING_MARKERS) and not failed
    deploying = _has_any(structured or combined_upper, DEPLOYING_MARKERS) and not failed
    running = _has_any(structured, RUNNING_MARKERS) and not failed and not crashed
    if not running and _has_any(combined_upper, RUNNING_MARKERS) and not failed and not crashed and not building and not deploying:
        running = True
    suspended = _has_any(structured or combined_upper, SUSPENDED_MARKERS)

    if crashed and (running or failed or "RUNNING" in structured):
        state = "RUNNING_THEN_CRASHED"
    elif failed:
        state = "FAILED"
    elif building:
        state = "BUILDING"
    elif deploying:
        state = "DEPLOYING"
    elif running:
        state = "RUNNING"
    elif suspended:
        state = "SUSPENDED"
    elif not statuses and not (deployment_get_raw or "").strip() and not (deployment_list_raw or "").strip():
        # No evidence yet after create — treat as still provisioning, not UNKNOWN.
        state = "BUILDING"
    else:
        state = "UNKNOWN"

    service_exec_allowed = state == "RUNNING"
    return {
        "P2_MIGRATION_DEPLOYMENT_STATUS": state,
        "P2_MIGRATION_BUILD_STATUS": "FAILED"
        if state in {"FAILED", "RUNNING_THEN_CRASHED"}
        else ("BUILDING" if state == "BUILDING" else ("READY" if state == "RUNNING" else state)),
        "P2_MIGRATION_RUNTIME_STATUS": "CRASHED"
        if state == "RUNNING_THEN_CRASHED"
        else ("RUNNING" if state == "RUNNING" else ("NOT_RUNNING" if state != "UNKNOWN" else "UNKNOWN")),
        "P2_MIGRATION_BUILD_LOG_TAIL": sanitize_log_tail(build_log_raw),
        "P2_MIGRATION_RUNTIME_LOG_TAIL": sanitize_log_tail(runtime_log_raw),
        "service_exec_allowed": service_exec_allowed,
        "wait_for_deployment": state in {"BUILDING", "DEPLOYING"},
        # UNKNOWN is fail-closed after wait timeout; do not allow service-exec.
        "fail_closed": state in {"FAILED", "RUNNING_THEN_CRASHED", "UNKNOWN", "SUSPENDED"},
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def wait_for_deployment_running(
    *,
    probe: Callable[[int], dict[str, str]],
    max_attempts: int = 24,
    interval_sec: float = 10.0,
    sleep: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Poll deployment diagnostics until RUNNING, or fail closed.

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
        )
        row = {"attempt": attempt, **classified}
        history.append(row)
        last = classified
        if classified["service_exec_allowed"]:
            return {
                "ready_for_service_exec": True,
                "attempts": attempt,
                "history": history,
                **classified,
            }
        if classified["wait_for_deployment"]:
            sleeper(interval_sec)
            continue
        if classified["P2_MIGRATION_DEPLOYMENT_STATUS"] == "UNKNOWN":
            # Keep polling until timeout; UNKNOWN alone must not unlock service-exec.
            sleeper(interval_sec)
            continue
        # FAILED / SUSPENDED / CRASHED — fail closed immediately.
        return {
            "ready_for_service_exec": False,
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


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment-get", default="")
    parser.add_argument("--deployment-list", default="")
    parser.add_argument("--build-log", default="")
    parser.add_argument("--runtime-log", default="")
    parser.add_argument("--emit-env", action="store_true")
    parser.add_argument("--write-artifact", default="")
    args = parser.parse_args(argv)

    def _read(path: str) -> str:
        if not path:
            return ""
        return Path(path).read_text(encoding="utf-8", errors="replace")

    classified = classify_deployment_snapshot(
        deployment_get_raw=_read(args.deployment_get),
        deployment_list_raw=_read(args.deployment_list),
        build_log_raw=_read(args.build_log),
        runtime_log_raw=_read(args.runtime_log),
    )
    print(json.dumps(classified, sort_keys=True))
    if args.emit_env:
        for key in (
            "P2_MIGRATION_DEPLOYMENT_STATUS",
            "P2_MIGRATION_BUILD_STATUS",
            "P2_MIGRATION_RUNTIME_STATUS",
        ):
            print(f"{key}={classified[key]}")
        print("P2_MIGRATION_BUILD_LOG_TAIL=<<BEGIN")
        print(classified.get("P2_MIGRATION_BUILD_LOG_TAIL") or "")
        print("P2_MIGRATION_BUILD_LOG_TAIL=<<END")
        print("P2_MIGRATION_RUNTIME_LOG_TAIL=<<BEGIN")
        print(classified.get("P2_MIGRATION_RUNTIME_LOG_TAIL") or "")
        print("P2_MIGRATION_RUNTIME_LOG_TAIL=<<END")
        print(f"service_exec_allowed={str(classified['service_exec_allowed']).lower()}")
        print(f"wait_for_deployment={str(classified['wait_for_deployment']).lower()}")
        print(f"fail_closed={str(classified['fail_closed']).lower()}")
    if args.write_artifact:
        out = Path(args.write_artifact)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(classified, indent=2), encoding="utf-8")
    if classified["service_exec_allowed"]:
        return 0
    if classified["wait_for_deployment"]:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
