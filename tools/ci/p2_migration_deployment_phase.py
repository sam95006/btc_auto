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

    list_payload = _parse_json_blob(deployment_list_raw or "")
    semantic = detect_deployment_record_semantic_error(deployment_list_raw or "", build_log_raw or "")
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
    parser.add_argument("--deployment-list-file", default="")
    parser.add_argument("--build-log-file", default="")
    parser.add_argument("--bootstrap-deployment-id", default="")
    parser.add_argument("--activation-started", action="store_true")
    parser.add_argument("--prior-build-hash", default="")
    parser.add_argument("--stall-count", type=int, default=0)
    parser.add_argument("--can-start-activation", action="store_true")
    parser.add_argument("--bootstrap-phase-json", default="")
    parser.add_argument("--emit-env", action="store_true")
    args = parser.parse_args(argv)

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

    list_raw = ""
    build_raw = ""
    if args.deployment_list_file:
        list_raw = Path(args.deployment_list_file).read_text(encoding="utf-8", errors="replace")
    if args.build_log_file:
        build_raw = Path(args.build_log_file).read_text(encoding="utf-8", errors="replace")

    result = evaluate_exact_deployment_phase(
        target_deployment_id=args.target_deployment_id,
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
