#!/usr/bin/env python3
"""Preflight for founder-approved 6H bounded Bybit Demo autonomous session."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib import error, request

from backend.nexus_bounded_runtime.durable_lease_store import _is_ephemeral_path
from backend.nexus_bounded_runtime.runtime_lease_storage_proof import (
    consume_remote_storage_proof,
    prove_runtime_durable_lease_storage,
)
from backend.nexus_demo_execution.demo_domain import DEMO_REST_BASE_URL
from backend.nexus_demo_execution.kill_switch import KillSwitch
from backend.nexus_demo_execution.p1_validation_runtime import apply_disarmed_flags
from backend.nexus_demo_execution.p2_run8_learning_closure import RepeatMistakeGuard
from backend.nexus_demo_execution.safety_gate import DemoExecutionSafetyGate
from backend.nexus_demo_execution.session_limits import FIXED_LEVERAGE, MARGIN_PER_TRADE_CAP
from tools.ci.demo_6h_v2_preflight import run_preflight as run_validation_preflight
from tools.ci.demo_bounded_session_lease import demo_api_base_ok
from tools.ci.p2_migration_service_identity import (
    LEARNING_VALIDATION_SERVICE_NAME,
    learning_validation_origin,
)

# Canonical bounded-Demo control-plane origin (env override else the live long
# domain). The dead short alias nexus-bybit-demo-val is never the default.
VALIDATION_URL = learning_validation_origin()


def _env_false(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() == "false"


def _get(url: str) -> tuple[dict[str, Any] | None, int | str]:
    try:
        with request.urlopen(request.Request(url, method="GET"), timeout=45) as resp:
            body = json.loads(resp.read().decode())
            return (body if isinstance(body, dict) else {"payload": body}), int(resp.status)
    except error.HTTPError as exc:
        return {"error": True, "status": exc.code}, int(exc.code)
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__}, f"ERR:{type(exc).__name__}"


def _health_sha(health: dict[str, Any] | None) -> str:
    if not health:
        return ""
    for key in ("github_sha", "GITHUB_SHA", "deployment_commit", "commit_sha", "git_sha"):
        value = health.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    runtime = health.get("runtime_identity")
    if isinstance(runtime, dict):
        for key in ("github_sha", "deployment_commit", "commit_sha"):
            value = runtime.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _repeat_mistake_guard_healthy() -> bool:
    guard = RepeatMistakeGuard(_EmptyMemory())
    result = guard.evaluate(
        {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "confidence": 0.5,
            "expected_gross_pnl": "1",
            "round_trip_fee_estimate": "0.1",
        }
    )
    return result.get("policy_mutated") is False and result.get("decision_after_learning") == "ALLOW"


class _EmptyMemory:
    def query_context(self, _candidate: dict[str, Any]) -> list:
        return []


def _offline_storage_root() -> Path:
    for key in ("NEXUS_DATA_ROOT", "NEXUS_DATA_DIR", "DATA_ROOT"):
        value = (os.environ.get(key) or "").strip()
        if value and not _is_ephemeral_path(Path(value)):
            return Path(value).resolve()
    return Path("artifacts/bounded_runtime_storage").resolve()


def _apply_db_checks(
    checks: dict[str, Any], problems: list[str], *, offline: bool, db_proof: dict[str, Any] | None
) -> None:
    """Populate the Postgres checks. The DB proof is obtained INSIDE the validation
    runtime (via zeabur service exec over the private network) and consumed here as
    sanitized boolean markers — the GitHub runner NEVER opens Postgres or holds the
    DSN. Fails closed when the in-runtime proof is missing or any marker is False."""
    checks["UNRESOLVED_INTENT_BLOCKS_ENTRY"] = True
    if offline:
        for key in (
            "POSTGRES_AVAILABLE", "MIGRATION_0007_PRESENT", "DURABLE_LESSONS_READABLE",
            "DURABLE_ORDER_LEDGER_READABLE", "NO_UNRESOLVED_ORPHAN_INTENTS", "NO_UNKNOWN_OUTCOME_STATE",
            "DURABLE_LEDGER_ENTRY_READY", "DB_PROOF_FROM_VALIDATION_RUNTIME",
        ):
            checks[key] = True
        return
    if db_proof is None:
        checks["POSTGRES_AVAILABLE"] = False
        checks["DB_PROOF_FROM_VALIDATION_RUNTIME"] = False
        problems.append("inruntime_db_proof_missing")
        return
    checks["POSTGRES_AVAILABLE"] = db_proof.get("POSTGRES_AVAILABLE") is True
    checks["MIGRATION_0007_PRESENT"] = db_proof.get("MIGRATION_0007_PRESENT") is True
    checks["DURABLE_LESSONS_READABLE"] = db_proof.get("DURABLE_LESSONS_READABLE") is True
    checks["DURABLE_ORDER_LEDGER_READABLE"] = db_proof.get("DURABLE_ORDER_LEDGER_READABLE") is True
    checks["NO_UNRESOLVED_ORPHAN_INTENTS"] = db_proof.get("NO_UNRESOLVED_ORPHAN_INTENTS") is True
    checks["NO_UNKNOWN_OUTCOME_STATE"] = db_proof.get("NO_UNKNOWN_OUTCOME_STATE") is True
    # Honest durable-state-clean signal from the READ-ONLY in-runtime proof (NOT a
    # reconciliation — no durable state was mutated to produce it).
    checks["DURABLE_LEDGER_ENTRY_READY"] = db_proof.get("DURABLE_LEDGER_ENTRY_READY") is True
    checks["DB_PROOF_FROM_VALIDATION_RUNTIME"] = db_proof.get("INRUNTIME_POSTGRES_PREFLIGHT_PASS") is True
    if db_proof.get("VALIDATION_RUNTIME_POSTGRES_MISSING") is True:
        problems.append("validation_runtime_postgres_missing")
    if not checks["NO_UNRESOLVED_ORPHAN_INTENTS"]:
        problems.append("unresolved_or_orphan_intent")
    if not checks["NO_UNKNOWN_OUTCOME_STATE"]:
        problems.append("unknown_outcome_ledger_state")
    if not checks["MIGRATION_0007_PRESENT"]:
        problems.append("migration_0007_missing")
    if not checks["DURABLE_ORDER_LEDGER_READABLE"]:
        problems.append("durable_order_ledger_unreadable")
    if not checks["DURABLE_LEDGER_ENTRY_READY"]:
        problems.append("durable_ledger_entry_not_ready")
    if not checks["DB_PROOF_FROM_VALIDATION_RUNTIME"]:
        problems.append("inruntime_db_proof_not_passed")


def run_preflight(
    *,
    base_url: str = VALIDATION_URL,
    expected_github_sha: str = "",
    postgres_url: str = "",
    founder_phrase: str = "",
    service_name: str = LEARNING_VALIDATION_SERVICE_NAME,
    offline: bool = False,
    db_proof: dict[str, Any] | None = None,
) -> dict[str, Any]:
    apply_disarmed_flags()
    evidence: dict[str, Any] = {
        "preflight_pass": False,
        "hold_reason": None,
        "checks": {},
        "problems": [],
    }
    checks = evidence["checks"]
    problems: list[str] = evidence["problems"]

    checks["MAINNET_FALSE"] = _env_false("MAINNET")
    checks["REAL_MONEY_FALSE"] = _env_false("REAL_MONEY")
    checks["EXCHANGE_WRITE_FALSE"] = _env_false("EXCHANGE_WRITE")
    checks["DEMO_AUTONOMOUS_ENABLED_FALSE"] = _env_false("DEMO_AUTONOMOUS_ENABLED")
    checks["AUTONOMOUS_SEND_FALSE"] = _env_false("AUTONOMOUS_SEND")
    checks["BYBIT_DEMO_ONLY"] = demo_api_base_ok(DEMO_REST_BASE_URL)
    checks["SERVICE_IS_LEARNING_VALIDATION"] = service_name == LEARNING_VALIDATION_SERVICE_NAME
    checks["RISK_ENGINE_FINAL_AUTHORITY"] = FIXED_LEVERAGE == 25 and float(MARGIN_PER_TRADE_CAP) == 20.0
    checks["REPEAT_MISTAKE_GUARD_HEALTHY"] = _repeat_mistake_guard_healthy()
    checks["RUNTIME_STORAGE_PROOF_NOT_GITHUB_RUNNER"] = False
    remote_storage: dict[str, Any] = {}
    if offline:
        offline_root = _offline_storage_root()
        runtime_proof = prove_runtime_durable_lease_storage(offline_root)
        remote_storage = consume_remote_storage_proof(runtime_proof)
        checks["DURABLE_LEASE_STORAGE_RUNTIME_PROVEN"] = remote_storage.get("DURABLE_LEASE_STORAGE_RUNTIME_PROVEN") is True
        checks["EPHEMERAL_LEASE_STORAGE"] = runtime_proof.get("EPHEMERAL_LEASE_STORAGE") is True
        checks["DURABLE_LEASE_STORAGE_PREFLIGHT_PASS"] = remote_storage.get("DURABLE_LEASE_STORAGE_PREFLIGHT_PASS") is True
        checks["EPHEMERAL_LEASE_STORAGE_REJECTED"] = runtime_proof.get("EPHEMERAL_LEASE_STORAGE") is False
        if not checks["DURABLE_LEASE_STORAGE_PREFLIGHT_PASS"]:
            problems.append("durable_lease_storage_not_proven")
    else:
        checks["DURABLE_LEASE_STORAGE_PREFLIGHT_PASS"] = False
        checks["DURABLE_LEASE_STORAGE_RUNTIME_PROVEN"] = False
        checks["EPHEMERAL_LEASE_STORAGE"] = True
        checks["EPHEMERAL_LEASE_STORAGE_REJECTED"] = False

    checks["CERTIFIED_BOUNDED_RUNTIME_ACTIVE"] = offline
    if not offline:
        status_payload, status_code = _get(f"{base_url.rstrip('/')}/api/nexus/demo-execution/bounded-6h/status")
        bounded = status_payload.get("bounded_6h") if isinstance(status_payload, dict) and isinstance(status_payload.get("bounded_6h"), dict) else status_payload
        if not isinstance(bounded, dict):
            bounded = {}
        if isinstance(bounded, dict):
            checks["CERTIFIED_BOUNDED_RUNTIME_ACTIVE"] = bounded.get("CERTIFIED_BOUNDED_RUNTIME_ACTIVE") is True
            remote_storage = consume_remote_storage_proof(bounded)
            checks["DURABLE_LEASE_STORAGE_RUNTIME_PROVEN"] = remote_storage.get("DURABLE_LEASE_STORAGE_RUNTIME_PROVEN") is True
            checks["EPHEMERAL_LEASE_STORAGE"] = remote_storage.get("EPHEMERAL_LEASE_STORAGE") is True
            checks["DURABLE_LEASE_STORAGE_PREFLIGHT_PASS"] = remote_storage.get("DURABLE_LEASE_STORAGE_PREFLIGHT_PASS") is True
            checks["RUNTIME_STORAGE_PROOF_NOT_GITHUB_RUNNER"] = remote_storage.get("RUNTIME_STORAGE_PROOF_NOT_GITHUB_RUNNER") is True
            checks["EPHEMERAL_LEASE_STORAGE_REJECTED"] = remote_storage.get("EPHEMERAL_LEASE_STORAGE") is False
            if status_code != 200:
                problems.append("runtime_storage_status_unreachable")
            if not checks["DURABLE_LEASE_STORAGE_RUNTIME_PROVEN"]:
                problems.append("runtime_durable_lease_storage_not_proven")
            if checks["EPHEMERAL_LEASE_STORAGE"]:
                problems.append("runtime_ephemeral_lease_storage")
            if not checks["RUNTIME_STORAGE_PROOF_NOT_GITHUB_RUNNER"]:
                problems.append("runtime_storage_proof_not_from_validation_service")
        else:
            checks["CERTIFIED_BOUNDED_RUNTIME_ACTIVE"] = False
            problems.append("runtime_bounded_status_missing")

    gate = DemoExecutionSafetyGate()
    kill = KillSwitch(gate)
    checks["KILL_SWITCH_HEALTHY"] = not kill.engaged

    if founder_phrase and founder_phrase.strip() != "START_NEXUS_BYBIT_DEMO_BOUNDED_6H_SESSION":
        problems.append("founder_phrase_invalid")
    checks["FOUNDER_AUTHORIZATION_VALID"] = founder_phrase.strip() == "START_NEXUS_BYBIT_DEMO_BOUNDED_6H_SESSION" if founder_phrase else False

    validation = run_validation_preflight(base=base_url) if not offline else {"6h_v2_ready": True, "http": {"health": 200}}
    health_code = validation.get("http", {}).get("health")
    health_payload, _ = _get(f"{base_url.rstrip('/')}/health") if not offline else ({"service": service_name}, 200)
    deployed_sha = _health_sha(health_payload)
    expected = (expected_github_sha or os.environ.get("GITHUB_SHA") or "").strip()
    checks["GITHUB_SHA_CONFIRMED"] = bool(expected) and (
        deployed_sha.lower() == expected.lower()
        if deployed_sha and len(expected) == 40 and len(deployed_sha) == 40
        else offline
    )
    if not offline and expected and deployed_sha and not checks["GITHUB_SHA_CONFIRMED"]:
        problems.append("github_sha_mismatch")

    checks["VALIDATION_HEALTH_OK"] = health_code == 200 or offline
    checks["ACCOUNT_FLAT"] = offline or (
        int(validation.get("position_count") or 0) == 0 and int(validation.get("open_order_count") or 0) == 0
    )
    checks["CLEAN_STARTING_ACCOUNT"] = checks["ACCOUNT_FLAT"]
    checks["RECONCILE_OPEN_ORDERS"] = checks["ACCOUNT_FLAT"]
    checks["RECONCILE_POSITIONS"] = checks["ACCOUNT_FLAT"]

    _apply_db_checks(checks, problems, offline=offline, db_proof=db_proof)

    for key in (
        "MAINNET_FALSE",
        "REAL_MONEY_FALSE",
        "EXCHANGE_WRITE_FALSE",
        "BYBIT_DEMO_ONLY",
        "SERVICE_IS_LEARNING_VALIDATION",
        "RISK_ENGINE_FINAL_AUTHORITY",
        "REPEAT_MISTAKE_GUARD_HEALTHY",
        "KILL_SWITCH_HEALTHY",
        "VALIDATION_HEALTH_OK",
        "CLEAN_STARTING_ACCOUNT",
        "NO_UNRESOLVED_ORPHAN_INTENTS",
        "NO_UNKNOWN_OUTCOME_STATE",
        "MIGRATION_0007_PRESENT",
        "DURABLE_LESSONS_READABLE",
        "DURABLE_ORDER_LEDGER_READABLE",
        "DURABLE_LEDGER_ENTRY_READY",
        "DB_PROOF_FROM_VALIDATION_RUNTIME",
        "CERTIFIED_BOUNDED_RUNTIME_ACTIVE",
        "DURABLE_LEASE_STORAGE_PREFLIGHT_PASS",
        "DURABLE_LEASE_STORAGE_RUNTIME_PROVEN",
        "EPHEMERAL_LEASE_STORAGE_REJECTED",
    ):
        if key == "EPHEMERAL_LEASE_STORAGE_REJECTED":
            if checks.get("EPHEMERAL_LEASE_STORAGE") is True:
                problems.append("ephemeral_lease_storage")
            continue
        if not checks.get(key):
            problems.append(key.lower())

    if not offline and not checks.get("RUNTIME_STORAGE_PROOF_NOT_GITHUB_RUNNER"):
        if "runtime_storage_proof_not_from_validation_service" not in problems:
            problems.append("runtime_storage_proof_not_from_validation_service")

    if founder_phrase and not checks.get("FOUNDER_AUTHORIZATION_VALID"):
        problems.append("founder_authorization_invalid")

    evidence["preflight_pass"] = len(problems) == 0
    if not evidence["preflight_pass"]:
        evidence["hold_reason"] = problems[0] if problems else "preflight_failed"
    evidence["validation_preflight"] = validation
    evidence["deployed_github_sha"] = deployed_sha
    evidence["expected_github_sha"] = expected
    evidence["demo_api_base"] = DEMO_REST_BASE_URL
    evidence["remote_durable_lease_storage"] = remote_storage
    evidence["REMOTE_DURABLE_LEASE_STORAGE_PROOF_PASS"] = checks.get("DURABLE_LEASE_STORAGE_PREFLIGHT_PASS") is True and (
        offline or checks.get("RUNTIME_STORAGE_PROOF_NOT_GITHUB_RUNNER") is True
    )
    return evidence


def parse_db_proof(text: str) -> dict[str, Any]:
    """Parse the sanitized in-runtime Postgres preflight markers (KEY=true/false
    lines produced by tools.ci.inruntime_postgres_preflight inside the validation
    service) into a boolean dict. Non-marker lines are ignored."""
    proof: dict[str, Any] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.isupper():
            proof[key] = value.strip().lower() == "true"
    return proof


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=VALIDATION_URL)
    parser.add_argument("--expected-sha", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--founder-phrase", default=os.environ.get("FOUNDER_BOUNDED_SESSION_PHRASE", ""))
    parser.add_argument("--offline", action="store_true")
    parser.add_argument(
        "--db-proof-file",
        default="",
        help="Path to sanitized in-runtime Postgres preflight markers (from zeabur service exec).",
    )
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    db_proof = None
    if args.db_proof_file:
        db_proof = parse_db_proof(Path(args.db_proof_file).read_text(encoding="utf-8"))
    report = run_preflight(
        base_url=args.base.rstrip("/"),
        expected_github_sha=args.expected_sha,
        founder_phrase=args.founder_phrase,
        offline=args.offline,
        db_proof=db_proof,
    )
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0 if report.get("preflight_pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
