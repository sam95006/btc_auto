"""P2 migration Zeabur lifecycle command guards (restart/redeploy + deployment record).

Exit code 0 is never sufficient: semantic control-plane errors fail closed.
Does not modify operational readiness / SHA proof logic.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from tools.ci.p2_migration_deployment_diagnostics import (
    _parse_json_blob,
    detect_zeabur_cli_semantic_error,
)

OID24 = re.compile(r"^[0-9a-f]{24}$", re.I)

LIFECYCLE_SEMANTIC_ERROR_PATTERNS = (
    re.compile(r"restart service failed", re.I),
    re.compile(r"redeploy service failed", re.I),
    re.compile(r"INTERNAL_SERVER_ERROR", re.I),
    re.compile(r"Path:\s*\[restartService\]", re.I),
    re.compile(r"Path:\s*\[redeployService\]", re.I),
)

DEPLOYMENT_RECORD_SEMANTIC_ERROR_PATTERNS = (
    re.compile(r"browser_signature_banned", re.I),
    re.compile(r"access_denied", re.I),
    re.compile(r'"status"\s*:\s*403\b'),
    re.compile(r"\bHTTP\s*403\b", re.I),
    re.compile(r"\b403\b.*forbidden", re.I),
    re.compile(r"INTERNAL_SERVER_ERROR", re.I),
    re.compile(r"failed to get service", re.I),
    re.compile(r"failed to get deployment", re.I),
)


def detect_lifecycle_semantic_error(*blobs: str) -> str | None:
    for blob in blobs:
        text = blob or ""
        if not text.strip():
            continue
        for pattern in LIFECYCLE_SEMANTIC_ERROR_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(0)
    return detect_zeabur_cli_semantic_error(*blobs)


def detect_deployment_record_semantic_error(*blobs: str) -> str | None:
    for blob in blobs:
        text = blob or ""
        if not text.strip():
            continue
        for pattern in DEPLOYMENT_RECORD_SEMANTIC_ERROR_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(0)
    return detect_lifecycle_semantic_error(*blobs)


def evaluate_lifecycle_command_pass(
    *,
    operation: str,
    exit_code: int | None,
    output: str,
) -> dict[str, Any]:
    """PASS only when exit is 0 AND no semantic control-plane error text."""
    op = (operation or "").strip().lower()
    if op not in {"restart", "redeploy"}:
        raise ValueError("lifecycle_operation_unsupported")
    semantic = detect_lifecycle_semantic_error(output or "")
    exit_ok = exit_code == 0
    ok = bool(exit_ok and semantic is None)
    result: dict[str, Any] = {
        "operation": op,
        "ok": ok,
        "exit_code": exit_code,
        "exit_ok": exit_ok,
        "cli_semantic_error": semantic or "",
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }
    if op == "restart":
        result["P2_MIGRATION_POST_VAR_RESTART"] = ok
        result["P2_MIGRATION_POST_VAR_RESTART_COUNT"] = 1 if ok else 0
        result["P2_MIGRATION_POST_VAR_RESTART_COMMAND_PASS"] = ok
    else:
        result["P2_MIGRATION_POST_VAR_REDEPLOY"] = ok
        result["P2_MIGRATION_POST_VAR_REDEPLOY_COUNT"] = 1 if ok else 0
        result["P2_MIGRATION_POST_VAR_REDEPLOY_COMMAND_PASS"] = ok
    return result


def _collect_oid24(payload: Any, *, into: list[str], limit: int = 40) -> None:
    if len(into) >= limit:
        return
    if isinstance(payload, dict):
        for key in ("_id", "id", "deployment_id", "deploymentId", "DeploymentID"):
            value = payload.get(key)
            if isinstance(value, str) and OID24.match(value.strip()):
                into.append(value.strip())
                if len(into) >= limit:
                    return
        for nested_key in (
            "deployment",
            "Deployment",
            "latestDeployment",
            "latest_deployment",
            "data",
            "result",
            "node",
        ):
            if nested_key in payload:
                _collect_oid24(payload[nested_key], into=into, limit=limit)
        for list_key in ("deployments", "Deployments", "edges", "items", "nodes"):
            items = payload.get(list_key)
            if isinstance(items, list):
                for item in items[:20]:
                    node = item.get("node") if isinstance(item, dict) else item
                    _collect_oid24(node, into=into, limit=limit)
    elif isinstance(payload, list):
        for item in payload[:20]:
            _collect_oid24(item, into=into, limit=limit)


def evaluate_deployment_record_present(
    *,
    deployment_get_raw: str = "",
    deployment_list_raw: str = "",
    deployment_get_exit: int | None = None,
    deployment_list_exit: int | None = None,
) -> dict[str, Any]:
    """True only when get/list yields a positive 24-hex deployment identity.

    Status/state/phase alone never counts. Exit 0 alone never counts.
    Semantic error envelopes fail closed. Does NOT require RUNNING.
    """
    get_raw = deployment_get_raw or ""
    list_raw = deployment_list_raw or ""
    semantic = detect_deployment_record_semantic_error(get_raw, list_raw)
    get_payload = _parse_json_blob(get_raw)
    list_payload = _parse_json_blob(list_raw)
    ids: list[str] = []
    _collect_oid24(get_payload, into=ids)
    _collect_oid24(list_payload, into=ids)
    seen: set[str] = set()
    unique_ids: list[str] = []
    for item in ids:
        if item not in seen:
            seen.add(item)
            unique_ids.append(item)

    present = bool(unique_ids) and semantic is None
    return {
        "ok": present,
        "P2_MIGRATION_DEPLOYMENT_RECORD_PRESENT": present,
        "deployment_id_count": len(unique_ids),
        "deployment_id_prefix": (unique_ids[0][:6] if unique_ids else ""),
        "deployment_get_exit": deployment_get_exit,
        "deployment_list_exit": deployment_list_exit,
        "cli_semantic_error": semantic or "",
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P2 migration lifecycle command classifier")
    parser.add_argument("--classify-lifecycle-file", default="")
    parser.add_argument("--exit-code", type=int, default=0)
    parser.add_argument("--operation", choices=("restart", "redeploy"), default="redeploy")
    parser.add_argument("--deployment-record", action="store_true")
    parser.add_argument("--deployment-get-file", default="")
    parser.add_argument("--deployment-list-file", default="")
    parser.add_argument("--deployment-get-exit", type=int, default=-1)
    parser.add_argument("--deployment-list-exit", type=int, default=-1)
    parser.add_argument("--emit-env", action="store_true")
    args = parser.parse_args(argv)

    if args.deployment_record:
        get_raw = Path(args.deployment_get_file).read_text(encoding="utf-8", errors="replace") if args.deployment_get_file else ""
        list_raw = (
            Path(args.deployment_list_file).read_text(encoding="utf-8", errors="replace")
            if args.deployment_list_file
            else ""
        )
        get_exit = None if args.deployment_get_exit < 0 else args.deployment_get_exit
        list_exit = None if args.deployment_list_exit < 0 else args.deployment_list_exit
        result = evaluate_deployment_record_present(
            deployment_get_raw=get_raw,
            deployment_list_raw=list_raw,
            deployment_get_exit=get_exit,
            deployment_list_exit=list_exit,
        )
        print(json.dumps(result, sort_keys=True))
        if args.emit_env:
            print(f"P2_MIGRATION_DEPLOYMENT_RECORD_PRESENT={str(result['ok']).lower()}")
            if get_exit is not None:
                print(f"DEPLOYMENT_GET_EXIT={get_exit}")
            if list_exit is not None:
                print(f"DEPLOYMENT_LIST_EXIT={list_exit}")
        return 0 if result["ok"] else 1

    if not args.classify_lifecycle_file:
        print("missing_classify_lifecycle_file", file=sys.stderr)
        return 2
    output = Path(args.classify_lifecycle_file).read_text(encoding="utf-8", errors="replace")
    result = evaluate_lifecycle_command_pass(
        operation=args.operation,
        exit_code=args.exit_code,
        output=output,
    )
    print(json.dumps(result, sort_keys=True))
    if args.emit_env:
        if args.operation == "redeploy":
            print(f"P2_MIGRATION_POST_VAR_REDEPLOY={str(result['ok']).lower()}")
            print(f"P2_MIGRATION_POST_VAR_REDEPLOY_COMMAND_PASS={str(result['ok']).lower()}")
            print(f"P2_MIGRATION_POST_VAR_REDEPLOY_COUNT={1 if result['ok'] else 0}")
        else:
            print(f"P2_MIGRATION_POST_VAR_RESTART={str(result['ok']).lower()}")
            print(f"P2_MIGRATION_POST_VAR_RESTART_COMMAND_PASS={str(result['ok']).lower()}")
            print(f"P2_MIGRATION_POST_VAR_RESTART_COUNT={1 if result['ok'] else 0}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
