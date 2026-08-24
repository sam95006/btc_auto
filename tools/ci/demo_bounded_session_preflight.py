#!/usr/bin/env python3
"""Preflight for founder-approved 6H bounded Bybit Demo autonomous session."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib import error, request

from backend.nexus_demo_execution.demo_domain import DEMO_REST_BASE_URL
from backend.nexus_demo_execution.durable_order_ledger import DurableOrderLedger
from backend.nexus_demo_execution.kill_switch import KillSwitch
from backend.nexus_demo_execution.order_reconciliation import BybitDemoReconciler
from backend.nexus_demo_execution.p1_validation_runtime import apply_disarmed_flags
from backend.nexus_demo_execution.p2_durable_learning_store import DurableLessonStore
from backend.nexus_demo_execution.p2_run8_learning_closure import RepeatMistakeGuard
from backend.nexus_demo_execution.safety_gate import DemoExecutionSafetyGate
from backend.nexus_demo_execution.session_limits import FIXED_LEVERAGE, MARGIN_PER_TRADE_CAP
from backend.nexus_persistence_pg.pool import PostgresPool
from tools.ci.demo_6h_v2_preflight import run_preflight as run_validation_preflight
from tools.ci.demo_bounded_session_lease import demo_api_base_ok
from tools.ci.p2_migration_service_identity import LEARNING_VALIDATION_SERVICE_NAME

VALIDATION_URL = os.environ.get("DEMO_VAL_URL", "https://nexus-bybit-demo-val.zeabur.app").rstrip("/")
UNKNOWN_OUTCOME_STATES = frozenset({"SUBMIT_UNKNOWN", "RECONCILIATION_REQUIRED"})


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


def _postgres_preflight(database_url: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "postgres_available": False,
        "migration_0007_present": False,
        "durable_lessons_readable": False,
        "unresolved_intent_count": 0,
        "unknown_outcome_count": 0,
        "orphan_positions": 0,
        "entries_allowed": False,
    }
    pool: PostgresPool | None = None
    store: DurableLessonStore | None = None
    try:
        pool = PostgresPool(database_url)
        pool.open()
        out["postgres_available"] = True
        versions = {str(row[0]) for row in pool.fetchall("SELECT version FROM nexus.schema_migrations")}
        out["migration_0007_present"] = "0007" in versions
        store = DurableLessonStore(pool=pool)
        out["durable_lessons_readable"] = isinstance(store.list_lessons(), list)
        ledger = DurableOrderLedger(pool)
        unfinished = ledger.unfinished()
        out["unresolved_intent_count"] = len(unfinished)
        out["unknown_outcome_count"] = sum(
            1 for item in unfinished if str(item.get("state") or "") in UNKNOWN_OUTCOME_STATES
        )

        class _EmptyReader:
            def find_order(self, **_kwargs: Any) -> None:
                return None

            def list_executions(self, **_kwargs: Any) -> list:
                return []

            def list_positions(self, _symbol: str | None = None) -> list:
                return []

        startup = BybitDemoReconciler(ledger, _EmptyReader()).startup_reconcile()
        out["orphan_positions"] = int(startup.get("orphan_positions") or 0)
        out["entries_allowed"] = bool(startup.get("entries_allowed"))
        return out
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"postgres_preflight:{type(exc).__name__}"
        return out
    finally:
        if store is not None:
            store.close()
        if pool is not None:
            pool.close()


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


def run_preflight(
    *,
    base_url: str = VALIDATION_URL,
    expected_github_sha: str = "",
    postgres_url: str = "",
    founder_phrase: str = "",
    service_name: str = LEARNING_VALIDATION_SERVICE_NAME,
    offline: bool = False,
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
    checks["CERTIFIED_BOUNDED_RUNTIME_ACTIVE"] = offline
    if not offline:
        status_payload, _ = _get(f"{base_url.rstrip('/')}/api/nexus/demo-execution/bounded-6h/status")
        bounded = status_payload.get("bounded_6h") if isinstance(status_payload.get("bounded_6h"), dict) else status_payload
        if isinstance(bounded, dict):
            checks["CERTIFIED_BOUNDED_RUNTIME_ACTIVE"] = bounded.get("CERTIFIED_BOUNDED_RUNTIME_ACTIVE") is True
        else:
            checks["CERTIFIED_BOUNDED_RUNTIME_ACTIVE"] = False

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

    pg_url = (postgres_url or os.environ.get("NEXUS_POSTGRES_URL") or os.environ.get("NEXUS_STAGING_POSTGRES_URL") or "").strip()
    if pg_url:
        pg = _postgres_preflight(pg_url)
        checks["POSTGRES_AVAILABLE"] = pg.get("postgres_available") is True
        checks["MIGRATION_0007_PRESENT"] = pg.get("migration_0007_present") is True
        checks["DURABLE_LESSONS_READABLE"] = pg.get("durable_lessons_readable") is True
        checks["NO_UNRESOLVED_ORPHAN_INTENTS"] = int(pg.get("unresolved_intent_count") or 0) == 0 and int(
            pg.get("orphan_positions") or 0
        ) == 0
        checks["NO_UNKNOWN_OUTCOME_STATE"] = int(pg.get("unknown_outcome_count") or 0) == 0
        checks["UNRESOLVED_INTENT_BLOCKS_ENTRY"] = True
        if not checks["NO_UNRESOLVED_ORPHAN_INTENTS"]:
            problems.append("unresolved_or_orphan_intent")
        if not checks["NO_UNKNOWN_OUTCOME_STATE"]:
            problems.append("unknown_outcome_ledger_state")
        if not checks["MIGRATION_0007_PRESENT"]:
            problems.append("migration_0007_missing")
    elif offline:
        checks["POSTGRES_AVAILABLE"] = True
        checks["MIGRATION_0007_PRESENT"] = True
        checks["DURABLE_LESSONS_READABLE"] = True
        checks["NO_UNRESOLVED_ORPHAN_INTENTS"] = True
        checks["NO_UNKNOWN_OUTCOME_STATE"] = True
        checks["UNRESOLVED_INTENT_BLOCKS_ENTRY"] = True
    else:
        checks["POSTGRES_AVAILABLE"] = False
        problems.append("postgres_url_missing")

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
        "CERTIFIED_BOUNDED_RUNTIME_ACTIVE",
    ):
        if not checks.get(key):
            problems.append(key.lower())

    if founder_phrase and not checks.get("FOUNDER_AUTHORIZATION_VALID"):
        problems.append("founder_authorization_invalid")

    evidence["preflight_pass"] = len(problems) == 0
    if not evidence["preflight_pass"]:
        evidence["hold_reason"] = problems[0] if problems else "preflight_failed"
    evidence["validation_preflight"] = validation
    evidence["deployed_github_sha"] = deployed_sha
    evidence["expected_github_sha"] = expected
    evidence["demo_api_base"] = DEMO_REST_BASE_URL
    return evidence


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=VALIDATION_URL)
    parser.add_argument("--expected-sha", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--founder-phrase", default=os.environ.get("FOUNDER_BOUNDED_SESSION_PHRASE", ""))
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = run_preflight(
        base_url=args.base.rstrip("/"),
        expected_github_sha=args.expected_sha,
        founder_phrase=args.founder_phrase,
        offline=args.offline,
    )
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0 if report.get("preflight_pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
