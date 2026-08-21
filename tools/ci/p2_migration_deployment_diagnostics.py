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
        for nested_key in ("deployment", "data", "result", "service"):
            nested = payload.get(nested_key)
            if nested is not None:
                found.extend(_status_strings(nested))
        for item in payload.get("deployments") or payload.get("edges") or []:
            node = item if not isinstance(item, dict) else item.get("node") or item
            found.extend(_status_strings(node))
    elif isinstance(payload, list):
        for item in payload[:5]:
            found.extend(_status_strings(item))
    return found


def _raw_hint_state(build_text: str, runtime_text: str, combined_text: str) -> str | None:
    """Raw unstructured text may hint BUILDING/DEPLOYING/FAILED/CRASHED only."""
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
    deployment_get_exit: int | None = None,
    deployment_list_exit: int | None = None,
    build_log_exit: int | None = None,
    runtime_log_exit: int | None = None,
) -> dict[str, Any]:
    get_exit = 0 if deployment_get_exit is None else int(deployment_get_exit)
    list_exit = 0 if deployment_list_exit is None else int(deployment_list_exit)
    build_exit = 0 if build_log_exit is None else int(build_log_exit)
    runtime_exit = 0 if runtime_log_exit is None else int(runtime_log_exit)

    get_payload = _parse_json_blob(deployment_get_raw) if get_exit == 0 else None
    list_payload = _parse_json_blob(deployment_list_raw) if list_exit == 0 else None
    # Malformed JSON (parse miss) with nonzero-looking content must not authorize RUNNING.
    statuses = _status_strings(get_payload) + _status_strings(list_payload)
    tokens = [normalize_status_token(item) for item in statuses]
    tokens = [token for token in tokens if token]
    structured_present = bool(tokens)

    build_text = build_log_raw or ""
    runtime_text = runtime_log_raw or ""
    combined_text = "\n".join(
        [
            deployment_get_raw or "",
            deployment_list_raw or "",
            build_text,
            runtime_text,
        ]
    )

    cli_failed = any(code != 0 for code in (get_exit, list_exit, build_exit, runtime_exit))
    # Primary structured get failure with no usable tokens → unknown/fail-closed, never RUNNING.
    structured_cli_unusable = get_exit != 0 or (get_exit == 0 and get_payload is None and bool((deployment_get_raw or "").strip()) and not tokens)

    negative_hit = next((token for token in tokens if token in NEGATIVE_TOKENS), "")
    positive_hit = next((token for token in tokens if token in POSITIVE_RUNNING_TOKENS), "")
    building_hit = next((token for token in tokens if token in BUILDING_TOKENS), "")
    deploying_hit = next((token for token in tokens if token in DEPLOYING_TOKENS), "")
    failed_hit = next((token for token in tokens if token in FAILED_TOKENS), "")
    crashed_hit = next((token for token in tokens if token in CRASHED_TOKENS), "")
    suspended_hit = next((token for token in tokens if token in SUSPENDED_TOKENS), "")

    state: str
    if structured_cli_unusable and not structured_present:
        state = "UNKNOWN"
    elif negative_hit in {"FAILED", "BUILD_FAILED", "DEPLOY_FAILED", "DEPLOYMENT_FAILED", "ERROR", "CRASHED"} or failed_hit or crashed_hit:
        state = "RUNNING_THEN_CRASHED" if crashed_hit or negative_hit == "CRASHED" else "FAILED"
    elif negative_hit in {"SUSPENDED", "INACTIVE", "STOPPED"} or suspended_hit:
        state = "SUSPENDED"
    elif negative_hit in {"NOT_RUNNING", "NOTRUNNING", "NOT_READY", "NOTREADY", "UNREADY"}:
        state = "NOT_RUNNING"
    elif positive_hit and structured_present and get_exit == 0 and get_payload is not None:
        # Exact positive token from parsed structured status only.
        state = "RUNNING"
    elif building_hit:
        state = "BUILDING"
    elif deploying_hit:
        state = "DEPLOYING"
    elif not structured_present:
        raw_state = _raw_hint_state(build_text, runtime_text, combined_text)
        if raw_state in {"FAILED", "RUNNING_THEN_CRASHED"}:
            state = raw_state
        elif raw_state in {"BUILDING", "DEPLOYING"}:
            state = raw_state
        elif not (deployment_get_raw or "").strip() and not (deployment_list_raw or "").strip() and get_exit == 0 and list_exit == 0:
            # Bounded initial empty evidence: still provisioning, never positive RUNNING.
            state = "BUILDING"
        else:
            state = "UNKNOWN"
    else:
        state = "UNKNOWN"

    # Hard rule: raw text / CLI noise containing "running" never upgrades to RUNNING.
    if state == "RUNNING" and (not structured_present or get_exit != 0 or get_payload is None):
        state = "UNKNOWN"

    service_exec_allowed = state == "RUNNING"
    return {
        "P2_MIGRATION_DEPLOYMENT_STATUS": state,
        "P2_MIGRATION_BUILD_STATUS": "FAILED"
        if state in {"FAILED", "RUNNING_THEN_CRASHED"}
        else ("BUILDING" if state == "BUILDING" else ("READY" if state == "RUNNING" else state)),
        "P2_MIGRATION_RUNTIME_STATUS": "CRASHED"
        if state == "RUNNING_THEN_CRASHED"
        else ("RUNNING" if state == "RUNNING" else ("NOT_RUNNING" if state not in {"UNKNOWN", "BUILDING", "DEPLOYING"} else state)),
        "P2_MIGRATION_BUILD_LOG_TAIL": sanitize_log_tail(build_log_raw),
        "P2_MIGRATION_RUNTIME_LOG_TAIL": sanitize_log_tail(runtime_log_raw),
        "structured_status_tokens": tokens,
        "deployment_get_exit": get_exit,
        "deployment_list_exit": list_exit,
        "build_log_exit": build_exit,
        "runtime_log_exit": runtime_exit,
        "cli_command_failed": cli_failed,
        "service_exec_allowed": service_exec_allowed,
        "wait_for_deployment": state in {"BUILDING", "DEPLOYING"},
        "fail_closed": state in {"FAILED", "RUNNING_THEN_CRASHED", "UNKNOWN", "SUSPENDED", "NOT_RUNNING"},
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
            deployment_get_exit=raw.get("deployment_get_exit"),  # type: ignore[arg-type]
            deployment_list_exit=raw.get("deployment_list_exit"),  # type: ignore[arg-type]
            build_log_exit=raw.get("build_log_exit"),  # type: ignore[arg-type]
            runtime_log_exit=raw.get("runtime_log_exit"),  # type: ignore[arg-type]
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
            sleeper(interval_sec)
            continue
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


def parse_zeabur_deployment_help(help_text: str) -> dict[str, Any]:
    text = help_text or ""
    lower = text.lower()
    supports_service_name = "--service-name" in lower or "service-name" in lower
    supports_service_id = "--service-id" in lower or "service-id" in lower
    supports_list = bool(re.search(r"\blist\b", lower))
    preferred = "service-name" if supports_service_name else ("service-id" if supports_service_id else "none")
    return {
        "supports_service_name": supports_service_name,
        "supports_service_id": supports_service_id,
        "supports_deployment_list": supports_list,
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
    parser.add_argument("--deployment-get-exit", type=int, default=0)
    parser.add_argument("--deployment-list-exit", type=int, default=0)
    parser.add_argument("--build-log-exit", type=int, default=0)
    parser.add_argument("--runtime-log-exit", type=int, default=0)
    parser.add_argument("--emit-env", action="store_true")
    parser.add_argument("--write-artifact", default="")
    parser.add_argument("--parse-help-file", default="")
    args = parser.parse_args(argv)

    if args.parse_help_file:
        help_text = Path(args.parse_help_file).read_text(encoding="utf-8", errors="replace")
        parsed = parse_zeabur_deployment_help(help_text)
        print(json.dumps(parsed, sort_keys=True))
        return 0 if parsed["preferred_selector"] != "none" else 1

    def _read(path: str) -> str:
        if not path:
            return ""
        return Path(path).read_text(encoding="utf-8", errors="replace")

    classified = classify_deployment_snapshot(
        deployment_get_raw=_read(args.deployment_get),
        deployment_list_raw=_read(args.deployment_list),
        build_log_raw=_read(args.build_log),
        runtime_log_raw=_read(args.runtime_log),
        deployment_get_exit=args.deployment_get_exit,
        deployment_list_exit=args.deployment_list_exit,
        build_log_exit=args.build_log_exit,
        runtime_log_exit=args.runtime_log_exit,
    )
    print(json.dumps(classified, sort_keys=True))
    if args.emit_env:
        for key in (
            "P2_MIGRATION_DEPLOYMENT_STATUS",
            "P2_MIGRATION_BUILD_STATUS",
            "P2_MIGRATION_RUNTIME_STATUS",
        ):
            print(f"{key}={classified[key]}")
        print(f"deployment_get_exit={classified['deployment_get_exit']}")
        print(f"deployment_list_exit={classified['deployment_list_exit']}")
        print(f"build_log_exit={classified['build_log_exit']}")
        print(f"runtime_log_exit={classified['runtime_log_exit']}")
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
