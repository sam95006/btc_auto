"""Exact deployment-ID phase gates for P2 migration bootstrap → activation sequencing.

Prevents activation while bootstrap is BUILDING and isolates CANCELED history
from the current activation deployment authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from tools.ci.p2_migration_deployment_diagnostics import (
    _parse_json_blob,
    detect_zeabur_cli_semantic_error,
    normalize_status_token,
)
from tools.ci.p2_migration_lifecycle_command import detect_deployment_record_semantic_error

OID24 = re.compile(r"^[0-9a-f]{24}$", re.I)

BOOTSTRAP_READY_TOKENS = frozenset({"RUNNING", "READY", "ACTIVE"})
WAIT_TOKENS = frozenset({"BUILDING", "PENDING", "QUEUED", "WAITING", "DEPLOYING", "STARTING", "RESTARTING"})
CANCELED_TOKENS = frozenset({"CANCELED", "CANCELLED"})
FAILED_TOKENS = frozenset({"FAILED", "ERROR", "BUILD_FAILED", "DEPLOY_FAILED", "DEPLOYMENT_FAILED"})
CRASHED_TOKENS = frozenset({"CRASHED", "CRASH"})

STALL_OBSERVATIONS_NEEDED = 3


def collect_valid_deployment_ids(payload: Any) -> frozenset[str]:
    """Unique 24-hex deployment IDs from list payload — set semantics, not array order."""
    ids: set[str] = set()
    if payload is None:
        return frozenset()
    for obj in iter_deployment_objects(payload):
        did = _deployment_id_from_obj(obj)
        if did:
            ids.add(did)
    return frozenset(ids)


def audit_deploy_output_deployment_id(deploy_output: str, *, pinned_cli: bool = False) -> dict[str, Any]:
    """Audit deploy --json; pinned P2 CLI makes deployment_id control authority."""
    optional_id = extract_deployment_id_from_output(deploy_output or "")
    authority = bool(pinned_cli)
    return {
        "P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY": authority,
        "P2_MIGRATION_DEPLOYMENT_LIST_AUTHORITY": False,
        "P2_ZEABUR_DEPLOYMENT_ID_DIRECT_FROM_UPLOAD": authority and bool(optional_id),
        "deploy_output_deployment_id_present": bool(optional_id),
        "deploy_output_deployment_id_prefix": optional_id[:6] if optional_id else "",
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def evaluate_pinned_deploy_output(
    *,
    deploy_output: str,
    deploy_exit: int | None,
    expected_service_id: str,
    expected_environment_id: str,
    expected_project_id: str = "",
    phase: str = "bootstrap",
    bootstrap_deployment_id: str = "",
) -> dict[str, Any]:
    """Pinned P2 CLI: deployment_id must come directly from deploy --json upload result."""
    from tools.ci.p2_migration_bootstrap import extract_create_deploy_ids

    phase_norm = (phase or "").strip().lower()
    if phase_norm not in {"bootstrap", "activation"}:
        raise ValueError("deployment_phase_unsupported")
    expected_sid = (expected_service_id or "").strip()
    expected_env = (expected_environment_id or "").strip()
    expected_project = (expected_project_id or "").strip()
    if not expected_sid:
        raise ValueError("service_id_missing")
    if not expected_env:
        raise ValueError("environment_id_missing")

    text = deploy_output or ""
    semantic = detect_deployment_record_semantic_error(text)
    ids = extract_create_deploy_ids(text)
    deployment_id = (ids.get("deployment_id") or "").strip() or extract_deployment_id_from_output(text)
    returned_sid = (ids.get("service_id") or "").strip()
    returned_env = (ids.get("environment_id") or "").strip()
    returned_project = (ids.get("project_id") or "").strip()

    service_match = (not returned_sid) or returned_sid == expected_sid
    env_match = (not returned_env) or returned_env == expected_env
    project_match = (not expected_project) or (not returned_project) or returned_project == expected_project
    exit_ok = deploy_exit == 0
    id_ok = bool(deployment_id) and bool(OID24.match(deployment_id))
    distinct_ok = True
    if phase_norm == "activation":
        bootstrap_id = (bootstrap_deployment_id or "").strip()
        distinct_ok = bool(bootstrap_id) and deployment_id != bootstrap_id

    ok = bool(exit_ok and id_ok and service_match and env_match and project_match and distinct_ok and not semantic)
    return {
        "ok": ok,
        "phase": phase_norm,
        "deployment_id": deployment_id if id_ok else "",
        "deployment_id_prefix": deployment_id[:6] if id_ok else "",
        "exit_code": deploy_exit,
        "cli_semantic_error": semantic or "",
        "service_match": service_match,
        "environment_match": env_match,
        "project_match": project_match,
        "distinct_from_bootstrap": distinct_ok,
        "P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY": True,
        "P2_MIGRATION_DEPLOYMENT_LIST_AUTHORITY": False,
        "P2_ZEABUR_DEPLOYMENT_ID_DIRECT_FROM_UPLOAD": id_ok,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def deployment_obj_from_get_payload(payload: Any, target: str) -> dict[str, Any] | None:
    want = (target or "").strip()
    if not want or payload is None:
        return None
    if isinstance(payload, dict):
        if _deployment_id_from_obj(payload) == want:
            return payload
        for key in ("deployment", "Deployment", "data", "result", "node"):
            if key in payload:
                found = deployment_obj_from_get_payload(payload[key], want)
                if found:
                    return found
    return find_deployment_by_id(payload, want)


def evaluate_bootstrap_deployment_discovery(
    *,
    deployment_list_raw: str = "",
    deployment_list_exit: int | None = None,
) -> dict[str, Any]:
    """Fresh run-scoped service: exactly one list ID is bootstrap; audit-only, not control authority."""
    result = _evaluate_bootstrap_deployment_discovery_impl(
        deployment_list_raw=deployment_list_raw,
        deployment_list_exit=deployment_list_exit,
    )
    result["P2_MIGRATION_DEPLOYMENT_LIST_AUTHORITY"] = False
    return result


def _evaluate_bootstrap_deployment_discovery_impl(
    *,
    deployment_list_raw: str = "",
    deployment_list_exit: int | None = None,
) -> dict[str, Any]:
    semantic = detect_deployment_record_semantic_error(deployment_list_raw or "")
    payload = _parse_json_blob(deployment_list_raw or "")
    ids = collect_valid_deployment_ids(payload)
    count = len(ids)
    base: dict[str, Any] = {
        "deployment_list_exit": deployment_list_exit,
        "cli_semantic_error": semantic or "",
        "deployment_id_count": count,
        "P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_COUNT": count,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }
    if semantic:
        return {
            **base,
            "ok": False,
            "wait": False,
            "hard_fail": True,
            "P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_DISCOVERY_PASS": False,
            "bootstrap_deployment_id": "",
        }
    if count == 0:
        return {
            **base,
            "ok": False,
            "wait": True,
            "hard_fail": False,
            "P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_DISCOVERY_PASS": False,
            "bootstrap_deployment_id": "",
        }
    if count == 1:
        bootstrap_id = next(iter(ids))
        return {
            **base,
            "ok": True,
            "wait": False,
            "hard_fail": False,
            "P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_DISCOVERY_PASS": True,
            "P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_ID": bootstrap_id,
            "bootstrap_deployment_id": bootstrap_id,
            "bootstrap_deployment_id_prefix": bootstrap_id[:6],
        }
    return {
        **base,
        "ok": False,
        "wait": False,
        "hard_fail": True,
        "P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_DISCOVERY_PASS": False,
        "P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_MULTIPLICITY_FAIL": True,
        "bootstrap_deployment_id": "",
    }


def evaluate_activation_baseline(
    *,
    deployment_list_raw: str,
    expected_bootstrap_deployment_id: str,
) -> dict[str, Any]:
    """Before activation deploy, baseline must be exactly {bootstrap_id}."""
    expected = (expected_bootstrap_deployment_id or "").strip()
    if not expected or not OID24.match(expected):
        raise ValueError("bootstrap_deployment_id_missing")
    semantic = detect_deployment_record_semantic_error(deployment_list_raw or "")
    payload = _parse_json_blob(deployment_list_raw or "")
    ids = collect_valid_deployment_ids(payload)
    want = frozenset({expected})
    ok = ids == want and semantic is None
    return {
        "ok": ok,
        "baseline_deployment_ids": sorted(ids),
        "expected_baseline_ids": sorted(want),
        "P2_MIGRATION_ACTIVATION_BASELINE_ID_SET_PASS": ok,
        "cli_semantic_error": semantic or "",
        "deployment_id_count": len(ids),
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def evaluate_activation_deployment_discovery(
    *,
    baseline_deployment_ids: frozenset[str] | set[str] | list[str],
    deployment_list_raw: str = "",
    deployment_list_exit: int | None = None,
) -> dict[str, Any]:
    """After activation deploy: list diff audit-only, not control authority."""
    result = _evaluate_activation_deployment_discovery_impl(
        baseline_deployment_ids=baseline_deployment_ids,
        deployment_list_raw=deployment_list_raw,
        deployment_list_exit=deployment_list_exit,
    )
    result["P2_MIGRATION_DEPLOYMENT_LIST_AUTHORITY"] = False
    return result


def _evaluate_activation_deployment_discovery_impl(
    *,
    baseline_deployment_ids: frozenset[str] | set[str] | list[str],
    deployment_list_raw: str = "",
    deployment_list_exit: int | None = None,
) -> dict[str, Any]:
    semantic = detect_deployment_record_semantic_error(deployment_list_raw or "")
    payload = _parse_json_blob(deployment_list_raw or "")
    after_ids = collect_valid_deployment_ids(payload)
    baseline = frozenset(baseline_deployment_ids or frozenset())
    new_ids = after_ids - baseline
    new_count = len(new_ids)
    base: dict[str, Any] = {
        "baseline_deployment_ids": sorted(baseline),
        "after_deployment_ids": sorted(after_ids),
        "new_deployment_ids": sorted(new_ids),
        "deployment_list_exit": deployment_list_exit,
        "cli_semantic_error": semantic or "",
        "P2_MIGRATION_ACTIVATION_NEW_DEPLOYMENT_COUNT": new_count,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }
    if semantic:
        return {
            **base,
            "ok": False,
            "wait": False,
            "hard_fail": True,
            "P2_MIGRATION_ACTIVATION_DEPLOYMENT_DISCOVERY_PASS": False,
            "activation_deployment_id": "",
        }
    if new_count == 0:
        return {
            **base,
            "ok": False,
            "wait": True,
            "hard_fail": False,
            "P2_MIGRATION_ACTIVATION_DEPLOYMENT_DISCOVERY_PASS": False,
            "activation_deployment_id": "",
        }
    if new_count == 1:
        activation_id = next(iter(new_ids))
        return {
            **base,
            "ok": True,
            "wait": False,
            "hard_fail": False,
            "P2_MIGRATION_ACTIVATION_DEPLOYMENT_DISCOVERY_PASS": True,
            "P2_MIGRATION_ACTIVATION_DEPLOYMENT_ID": activation_id,
            "activation_deployment_id": activation_id,
            "activation_deployment_id_prefix": activation_id[:6],
        }
    return {
        **base,
        "ok": False,
        "wait": False,
        "hard_fail": True,
        "P2_MIGRATION_ACTIVATION_DEPLOYMENT_DISCOVERY_PASS": False,
        "P2_MIGRATION_ACTIVATION_DEPLOYMENT_MULTIPLICITY_FAIL": True,
        "activation_deployment_id": "",
    }


def discovery_exit_code(result: dict[str, Any]) -> int:
    if result.get("ok"):
        return 0
    if result.get("wait"):
        return 2
    return 1


def extract_deployment_id_from_output(raw: str) -> str:
    text = raw or ""
    for key in ("deployment_id", "deploymentId", "DeploymentID"):
        match = re.search(rf'"{re.escape(key)}"\s*:\s*"([0-9a-f]{{24}})"', text, re.I)
        if match:
            return match.group(1)
    match = re.search(r'"deployment"\s*:\s*\{[^}]*"_id"\s*:\s*"([0-9a-f]{24})"', text, re.I | re.S)
    if match:
        return match.group(1)
    return ""


def _deployment_id_from_obj(obj: dict[str, Any]) -> str:
    for key in ("_id", "id", "deployment_id", "deploymentId", "DeploymentID"):
        value = obj.get(key)
        if isinstance(value, str) and OID24.match(value.strip()):
            return value.strip()
    return ""


def iter_deployment_objects(payload: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            did = _deployment_id_from_obj(node)
            if did:
                found.append(node)
            for nested_key in ("deployment", "Deployment", "node", "data", "result"):
                if nested_key in node:
                    walk(node[nested_key])
            for list_key in ("deployments", "Deployments", "edges", "items", "nodes"):
                items = node.get(list_key)
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and "node" in item:
                            walk(item["node"])
                        else:
                            walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    # Deduplicate by id preserving order.
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for obj in found:
        did = _deployment_id_from_obj(obj)
        if did and did not in seen:
            seen.add(did)
            unique.append(obj)
    return unique


def find_deployment_by_id(payload: Any, deployment_id: str) -> dict[str, Any] | None:
    want = (deployment_id or "").strip()
    if not want:
        return None
    for obj in iter_deployment_objects(payload):
        if _deployment_id_from_obj(obj) == want:
            return obj
    return None


def deployment_status_token(deployment_obj: dict[str, Any] | None) -> str:
    if not deployment_obj:
        return "MISSING"
    tokens: list[str] = []
    for key in ("status", "Status", "state", "State", "phase", "Phase"):
        value = deployment_obj.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            tokens.append(normalize_status_token(str(value)))
    for token in tokens:
        if token:
            return token
    return "UNKNOWN"


def build_log_progress_hash(build_log: str) -> str:
    tail = (build_log or "")[-2000:]
    return hashlib.sha256(tail.encode("utf-8", errors="replace")).hexdigest()[:16]


def evaluate_exact_deployment_phase(
    *,
    target_deployment_id: str,
    deployment_get_raw: str = "",
    deployment_list_raw: str = "",
    build_log_raw: str = "",
    phase: str,
    bootstrap_deployment_id: str = "",
    activation_started: bool = False,
    prior_build_hash: str = "",
    stall_count: int = 0,
) -> dict[str, Any]:
    """Classify one exact deployment ID — never promotes BUILDING to ready."""
    target = (target_deployment_id or "").strip()
    if not target or not OID24.match(target):
        raise ValueError("deployment_id_missing")
    phase_norm = (phase or "").strip().lower()
    if phase_norm not in {"bootstrap", "activation"}:
        raise ValueError("deployment_phase_unsupported")

    get_payload = _parse_json_blob(deployment_get_raw or "")
    list_payload = _parse_json_blob(deployment_list_raw or "")
    semantic = detect_deployment_record_semantic_error(
        deployment_get_raw or deployment_list_raw or "",
        build_log_raw or "",
    )
    if deployment_get_raw:
        obj = deployment_obj_from_get_payload(get_payload, target)
    else:
        obj = find_deployment_by_id(list_payload, target)
    status = deployment_status_token(obj)
    progress_hash = build_log_progress_hash(build_log_raw or "")

    result: dict[str, Any] = {
        "target_deployment_id": target,
        "target_deployment_id_prefix": target[:6],
        "deployment_phase": phase_norm,
        "exact_status": status,
        "deployment_found": obj is not None,
        "build_log_progress_hash": progress_hash,
        "prior_build_log_progress_hash": prior_build_hash or "",
        "stall_count": stall_count,
        "cli_semantic_error": semantic or "",
        "P2_MIGRATION_DEPLOYMENT_LIST_AUTHORITY": False,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }

    if semantic:
        result.update(
            {
                "ready": False,
                "wait": False,
                "hard_fail": True,
                "P2_MIGRATION_BUILD_STALLED": False,
                "P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_SUPERSEDED": False,
            }
        )
        return result

    if obj is None:
        result.update({"ready": False, "wait": True, "hard_fail": False, "P2_MIGRATION_BUILD_STALLED": False})
        result["P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_SUPERSEDED"] = False
        return result

    if status in BOOTSTRAP_READY_TOKENS:
        result.update(
            {
                "ready": True,
                "wait": False,
                "hard_fail": False,
                "P2_MIGRATION_BUILD_STALLED": False,
                "P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_SUPERSEDED": False,
            }
        )
        if phase_norm == "bootstrap":
            result["P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_READY"] = True
        else:
            result["P2_MIGRATION_ACTIVATION_DEPLOYMENT_READY"] = True
        return result

    if status in WAIT_TOKENS:
        new_stall = stall_count
        if prior_build_hash and progress_hash == prior_build_hash:
            new_stall = stall_count + 1
        else:
            new_stall = 0
        stalled = new_stall >= STALL_OBSERVATIONS_NEEDED
        result.update(
            {
                "ready": False,
                "wait": not stalled,
                "hard_fail": stalled,
                "stall_count": new_stall,
                "P2_MIGRATION_BUILD_STALLED": stalled,
                "P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_SUPERSEDED": False,
            }
        )
        return result

    if status in CANCELED_TOKENS:
        bootstrap_id = (bootstrap_deployment_id or "").strip()
        superseded = (
            phase_norm == "bootstrap"
            and target == bootstrap_id
            and activation_started
        )
        result.update(
            {
                "ready": False,
                "wait": False,
                "hard_fail": True,
                "P2_MIGRATION_BUILD_STALLED": False,
                "P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_SUPERSEDED": superseded,
            }
        )
        return result

    if status in FAILED_TOKENS or status in CRASHED_TOKENS:
        result.update(
            {
                "ready": False,
                "wait": False,
                "hard_fail": True,
                "P2_MIGRATION_BUILD_STALLED": False,
                "P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_SUPERSEDED": False,
            }
        )
        return result

    # UNKNOWN / other — wait bounded, never pass.
    result.update(
        {
            "ready": False,
            "wait": True,
            "hard_fail": False,
            "P2_MIGRATION_BUILD_STALLED": False,
            "P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_SUPERSEDED": False,
        }
    )
    return result


def can_start_activation_deploy(*, bootstrap_phase: dict[str, Any]) -> dict[str, Any]:
    """Block activation local deploy while bootstrap deployment is not ready."""
    ready = bool(bootstrap_phase.get("ready"))
    status = bootstrap_phase.get("exact_status") or "UNKNOWN"
    blocked = not ready
    return {
        "ok": ready,
        "blocked": blocked,
        "P2_MIGRATION_ACTIVATION_BEFORE_BOOTSTRAP_READY_BLOCKED": blocked,
        "bootstrap_exact_status": status,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def gate_exit_code(phase_result: dict[str, Any]) -> int:
    if phase_result.get("ready"):
        return 0
    if phase_result.get("wait"):
        return 2
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P2 migration exact deployment phase gate")
    parser.add_argument("--evaluate-phase", action="store_true")
    parser.add_argument("--target-deployment-id", default="")
    parser.add_argument("--phase", choices=("bootstrap", "activation"), default="bootstrap")
    parser.add_argument("--deployment-get-file", default="")
    parser.add_argument("--deployment-list-file", default="")
    parser.add_argument("--build-log-file", default="")
    parser.add_argument("--evaluate-pinned-deploy", action="store_true")
    parser.add_argument("--deploy-output-file", default="")
    parser.add_argument("--deploy-exit", type=int, default=-1)
    parser.add_argument("--expected-service-id", default="")
    parser.add_argument("--expected-environment-id", default="")
    parser.add_argument("--expected-project-id", default="")
    parser.add_argument("--bootstrap-deployment-id", default="")
    parser.add_argument("--activation-started", action="store_true")
    parser.add_argument("--prior-build-hash", default="")
    parser.add_argument("--stall-count", type=int, default=0)
    parser.add_argument("--can-start-activation", action="store_true")
    parser.add_argument("--bootstrap-phase-json", default="")
    parser.add_argument("--emit-env", action="store_true")
    parser.add_argument("--discover-bootstrap", action="store_true")
    parser.add_argument("--discover-activation", action="store_true")
    parser.add_argument("--evaluate-baseline", action="store_true")
    parser.add_argument("--expected-bootstrap-deployment-id", default="")
    parser.add_argument("--baseline-ids", default="")
    parser.add_argument("--deployment-list-exit", type=int, default=-1)
    parser.add_argument("--audit-deploy-output-file", default="")
    args = parser.parse_args(argv)

    if args.audit_deploy_output_file:
        raw = Path(args.audit_deploy_output_file).read_text(encoding="utf-8", errors="replace")
        result = audit_deploy_output_deployment_id(raw)
        print(json.dumps(result, sort_keys=True))
        if args.emit_env:
            print("P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY=false")
            if result.get("deploy_output_deployment_id_present"):
                print(f"deploy_output_deployment_id_prefix={result['deploy_output_deployment_id_prefix']}")
        return 0

    list_raw = ""
    get_raw = ""
    build_raw = ""
    if args.deployment_get_file:
        get_raw = Path(args.deployment_get_file).read_text(encoding="utf-8", errors="replace")
    if args.deployment_list_file:
        list_raw = Path(args.deployment_list_file).read_text(encoding="utf-8", errors="replace")
    if args.build_log_file:
        build_raw = Path(args.build_log_file).read_text(encoding="utf-8", errors="replace")
    list_exit = None if args.deployment_list_exit < 0 else args.deployment_list_exit

    if args.evaluate_pinned_deploy:
        deploy_raw = ""
        if args.deploy_output_file:
            deploy_raw = Path(args.deploy_output_file).read_text(encoding="utf-8", errors="replace")
        deploy_exit = None if args.deploy_exit < 0 else args.deploy_exit
        result = evaluate_pinned_deploy_output(
            deploy_output=deploy_raw,
            deploy_exit=deploy_exit,
            expected_service_id=args.expected_service_id,
            expected_environment_id=args.expected_environment_id,
            expected_project_id=args.expected_project_id,
            phase=args.phase,
            bootstrap_deployment_id=args.bootstrap_deployment_id,
        )
        print(json.dumps(result, sort_keys=True))
        if args.emit_env:
            print("P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY=true")
            print("P2_MIGRATION_DEPLOYMENT_LIST_AUTHORITY=false")
            print(f"P2_ZEABUR_DEPLOYMENT_ID_DIRECT_FROM_UPLOAD={str(result.get('P2_ZEABUR_DEPLOYMENT_ID_DIRECT_FROM_UPLOAD', False)).lower()}")
            if result.get("deployment_id"):
                if args.phase == "bootstrap":
                    print(f"P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_ID={result['deployment_id']}")
                    print(f"bootstrap_deployment_id={result['deployment_id']}")
                else:
                    print(f"P2_MIGRATION_ACTIVATION_DEPLOYMENT_ID={result['deployment_id']}")
                    print(f"activation_deployment_id={result['deployment_id']}")
        return 0 if result["ok"] else 1

    if args.discover_bootstrap:
        result = evaluate_bootstrap_deployment_discovery(
            deployment_list_raw=list_raw,
            deployment_list_exit=list_exit,
        )
        print(json.dumps(result, sort_keys=True))
        if args.emit_env:
            print(f"P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_DISCOVERY_PASS={str(result.get('P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_DISCOVERY_PASS', False)).lower()}")
            print(f"P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_COUNT={result.get('deployment_id_count', 0)}")
            if result.get("bootstrap_deployment_id"):
                print(f"P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_ID={result['bootstrap_deployment_id']}")
                print(f"bootstrap_deployment_id={result['bootstrap_deployment_id']}")
        return discovery_exit_code(result)

    if args.evaluate_baseline:
        result = evaluate_activation_baseline(
            deployment_list_raw=list_raw,
            expected_bootstrap_deployment_id=args.expected_bootstrap_deployment_id,
        )
        print(json.dumps(result, sort_keys=True))
        if args.emit_env:
            print(f"P2_MIGRATION_ACTIVATION_BASELINE_ID_SET_PASS={str(result['ok']).lower()}")
        return 0 if result["ok"] else 1

    if args.discover_activation:
        baseline_parts = [p.strip() for p in (args.baseline_ids or "").split(",") if p.strip()]
        baseline = frozenset(baseline_parts)
        result = evaluate_activation_deployment_discovery(
            baseline_deployment_ids=baseline,
            deployment_list_raw=list_raw,
            deployment_list_exit=list_exit,
        )
        print(json.dumps(result, sort_keys=True))
        if args.emit_env:
            print(f"P2_MIGRATION_ACTIVATION_DEPLOYMENT_DISCOVERY_PASS={str(result.get('P2_MIGRATION_ACTIVATION_DEPLOYMENT_DISCOVERY_PASS', False)).lower()}")
            print(f"P2_MIGRATION_ACTIVATION_NEW_DEPLOYMENT_COUNT={result.get('P2_MIGRATION_ACTIVATION_NEW_DEPLOYMENT_COUNT', 0)}")
            if result.get("activation_deployment_id"):
                print(f"P2_MIGRATION_ACTIVATION_DEPLOYMENT_ID={result['activation_deployment_id']}")
                print(f"activation_deployment_id={result['activation_deployment_id']}")
        return discovery_exit_code(result)

    if args.can_start_activation:
        if args.bootstrap_phase_json:
            bootstrap = json.loads(Path(args.bootstrap_phase_json).read_text(encoding="utf-8"))
        else:
            bootstrap = json.loads(args.bootstrap_phase_json or "{}")
        result = can_start_activation_deploy(bootstrap_phase=bootstrap)
        print(json.dumps(result, sort_keys=True))
        if args.emit_env:
            print(f"P2_MIGRATION_ACTIVATION_BEFORE_BOOTSTRAP_READY_BLOCKED={str(result['blocked']).lower()}")
        return 0 if result["ok"] else 1

    result = evaluate_exact_deployment_phase(
        target_deployment_id=args.target_deployment_id,
        deployment_get_raw=get_raw,
        deployment_list_raw=list_raw,
        build_log_raw=build_raw,
        phase=args.phase,
        bootstrap_deployment_id=args.bootstrap_deployment_id,
        activation_started=args.activation_started,
        prior_build_hash=args.prior_build_hash,
        stall_count=args.stall_count,
    )
    print(json.dumps(result, sort_keys=True))
    if args.emit_env:
        print(f"deployment_phase={result['deployment_phase']}")
        print(f"exact_status={result['exact_status']}")
        print(f"build_log_progress_hash={result['build_log_progress_hash']}")
        print(f"target_deployment_id_prefix={result['target_deployment_id_prefix']}")
        if result.get("P2_MIGRATION_BUILD_STALLED"):
            print("P2_MIGRATION_BUILD_STALLED=true")
        if result.get("P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_SUPERSEDED"):
            print("P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_SUPERSEDED=true")
        if result.get("ready") and args.phase == "bootstrap":
            print("P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_READY=true")
        if result.get("ready") and args.phase == "activation":
            print("P2_MIGRATION_ACTIVATION_DEPLOYMENT_READY=true")
    return gate_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
