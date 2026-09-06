#!/usr/bin/env python3
"""IN-RUNTIME, strictly READ-ONLY Postgres preflight for the bounded-Demo plane.

Runs INSIDE the validation service (nexus-bybit-demo-learning-validation) via
`zeabur service exec`, using the service's OWN runtime NEXUS_POSTGRES_URL over the
Zeabur private network. The GitHub runner never needs the DSN; the PostgreSQL
Public Port stays OFF.

STRICTLY READ-ONLY: only PostgresPool SELECTs, schema_migrations, DurableLessonStore
.list_lessons(), and DurableOrderLedger.unfinished(). It NEVER calls startup
reconciliation, DurableOrderLedger.transition(), BybitDemoReconciler, or any
insert/update/delete — so a dry preflight can never mutate durable order state.
Prints ONLY sanitized boolean markers; never the DSN/credentials. Fails closed.
"""
from __future__ import annotations

import os
import sys

# Intents in these states are unresolved/unknown outcomes and block a new entry.
UNKNOWN_OUTCOME_STATES = frozenset({"SUBMIT_UNKNOWN", "RECONCILIATION_REQUIRED"})

MARKER_KEYS = (
    "POSTGRES_AVAILABLE",
    "MIGRATION_0007_PRESENT",
    "DURABLE_LESSONS_READABLE",
    "DURABLE_ORDER_LEDGER_READABLE",
    "NO_UNRESOLVED_ORPHAN_INTENTS",
    "NO_UNKNOWN_OUTCOME_STATE",
    "DURABLE_LEDGER_ENTRY_READY",
)


def _readonly_facts(database_url: str) -> dict:
    """Gather read-only durable-state facts. NEVER mutates: no startup_reconcile,
    no ledger.transition, no writes. Returns raw facts (never printed as-is)."""
    from backend.nexus_demo_execution.durable_order_ledger import DurableOrderLedger
    from backend.nexus_demo_execution.p2_durable_learning_store import DurableLessonStore
    from backend.nexus_persistence_pg.pool import PostgresPool

    facts: dict = {
        "postgres_available": False,
        "migration_0007_present": False,
        "durable_lessons_readable": False,
        "ledger_readable": False,
        "unresolved_intent_count": 0,
        "unknown_outcome_count": 0,
    }
    pool = None
    store = None
    try:
        pool = PostgresPool(database_url)
        pool.open()
        facts["postgres_available"] = True
        versions = {str(row[0]) for row in pool.fetchall("SELECT version FROM nexus.schema_migrations")}
        facts["migration_0007_present"] = "0007" in versions
        store = DurableLessonStore(pool=pool)
        facts["durable_lessons_readable"] = isinstance(store.list_lessons(), list)
        ledger = DurableOrderLedger(pool)
        unfinished = ledger.unfinished()  # pure SELECT — read-only
        facts["ledger_readable"] = isinstance(unfinished, list)
        facts["unresolved_intent_count"] = len(unfinished)
        facts["unknown_outcome_count"] = sum(
            1 for item in unfinished if str(item.get("state") or "") in UNKNOWN_OUTCOME_STATES
        )
        return facts
    except Exception as exc:  # noqa: BLE001 - never leak internals; fail closed
        facts["error"] = type(exc).__name__
        return facts
    finally:
        if store is not None:
            try:
                store.close()
            except Exception:  # noqa: BLE001
                pass
        if pool is not None:
            try:
                pool.close()
            except Exception:  # noqa: BLE001
                pass


def to_markers(facts: dict) -> dict[str, bool]:
    """Sanitized booleans only — no raw counts, no DSN. DURABLE_LEDGER_ENTRY_READY
    is an honest durable-state-clean signal (NOT a reconciliation)."""
    available = facts.get("postgres_available") is True
    markers = {
        "POSTGRES_AVAILABLE": available,
        "MIGRATION_0007_PRESENT": facts.get("migration_0007_present") is True,
        "DURABLE_LESSONS_READABLE": facts.get("durable_lessons_readable") is True,
        "DURABLE_ORDER_LEDGER_READABLE": facts.get("ledger_readable") is True and "error" not in facts,
        "NO_UNRESOLVED_ORPHAN_INTENTS": int(facts.get("unresolved_intent_count") or 0) == 0,
        "NO_UNKNOWN_OUTCOME_STATE": int(facts.get("unknown_outcome_count") or 0) == 0,
    }
    markers["DURABLE_LEDGER_ENTRY_READY"] = all(
        markers[key]
        for key in (
            "POSTGRES_AVAILABLE",
            "MIGRATION_0007_PRESENT",
            "DURABLE_ORDER_LEDGER_READABLE",
            "NO_UNRESOLVED_ORPHAN_INTENTS",
            "NO_UNKNOWN_OUTCOME_STATE",
        )
    )
    return markers


def all_pass(markers: dict[str, bool]) -> bool:
    return all(markers.get(key) is True for key in MARKER_KEYS)


def _emit(markers: dict[str, bool]) -> None:
    for key in MARKER_KEYS:
        print(f"{key}={'true' if markers.get(key) else 'false'}")


def main() -> int:
    dsn = (os.environ.get("NEXUS_POSTGRES_URL") or "").strip()
    if not dsn:
        print("VALIDATION_RUNTIME_POSTGRES_MISSING=true")
        print("INRUNTIME_POSTGRES_PREFLIGHT_PASS=false")
        return 1
    markers = to_markers(_readonly_facts(dsn))
    _emit(markers)
    ok = all_pass(markers)
    print(f"INRUNTIME_POSTGRES_PREFLIGHT_PASS={'true' if ok else 'false'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
