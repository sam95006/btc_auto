"""Read-only PostgreSQL / durability preflight for the certifier.

Runs INSIDE the private runtime over the Zeabur private network
(postgresql.zeabur.internal). Read-only: existence/availability/reconciliation
checks only — no INSERT/UPDATE/DELETE/DDL. Never returns DSN, password, user,
or database credentials. Fail-closed on any error.
"""

from __future__ import annotations

from typing import Any

# Durable stores (must be reachable). Names come from the migration catalog.
_LEDGER_TABLES = ("bybit_demo_order_intents", "bybit_demo_order_state_history")
_LESSON_TABLES = ("lesson_candidates",)
_LEARNING_TABLES = ("reflections", "lesson_candidates")
_GUARD_TABLES = ("decision_memory",)
_EVIDENCE_TABLES = ("runtime_evidence_events",)

# Durable order-ledger states that mean "needs reconciliation / unresolved".
_UNRESOLVED_STATES = ("SUBMIT_UNKNOWN", "RECONCILIATION_REQUIRED")


def _fail(reason: str) -> dict[str, Any]:
    return {
        "postgres_available": False,
        "reason": reason,
        "migration_catalog_valid": False,
        "migration_0007_present": False,
        "migration_0014_present": False,
        "durable_ledger_readable": False,
        "durable_lesson_readable": False,
        "learning_closure_readable": False,
        "repeat_mistake_guard_healthy": False,
        "runtime_lease_healthy": False,
        "cost_gate_healthy": False,
        "no_unresolved_intent": False,
    }


def postgres_durability_preflight(pool: Any) -> dict[str, Any]:
    if pool is None:
        return _fail("no_pool")
    try:
        readiness = pool.readiness()
    except Exception as exc:  # noqa: BLE001
        return _fail(f"readiness_error:{type(exc).__name__}")
    if not readiness.get("ready"):
        return _fail(str(readiness.get("reason") or "not_ready"))

    # Migration catalog (files) validity.
    try:
        from backend.nexus_persistence_pg.migrate import MigrationRunner

        catalog = MigrationRunner().validate()
        catalog_valid = bool(catalog.get("ok"))
    except Exception:  # noqa: BLE001
        catalog_valid = False

    # Applied migrations (read-only).
    try:
        applied_rows = pool.fetchall("SELECT version FROM nexus.schema_migrations")
        applied = {str(r[0]) for r in applied_rows}
    except Exception:  # noqa: BLE001
        applied = set()

    # Table existence (single read-only query).
    try:
        rows = pool.fetchall(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'nexus'"
        )
        present = {str(r[0]) for r in rows}
    except Exception:  # noqa: BLE001
        present = set()

    def has(tables: tuple[str, ...]) -> bool:
        return all(t in present for t in tables)

    # Unresolved durable ledger intents (read-only).
    no_unresolved = False
    if "bybit_demo_order_intents" in present:
        try:
            placeholders = ",".join(["%s"] * len(_UNRESOLVED_STATES))
            unresolved = pool.fetchval(
                f"SELECT COUNT(*) FROM nexus.bybit_demo_order_intents WHERE state IN ({placeholders})",
                tuple(_UNRESOLVED_STATES),
            )
            no_unresolved = int(unresolved or 0) == 0
        except Exception:  # noqa: BLE001
            no_unresolved = False

    return {
        "postgres_available": True,
        "reason": None,
        "migration_catalog_valid": catalog_valid,
        "migration_0007_present": "0007" in applied,
        "migration_0014_present": "0014" in applied,
        "durable_ledger_readable": has(_LEDGER_TABLES),
        "durable_lesson_readable": has(_LESSON_TABLES),
        "learning_closure_readable": has(_LEARNING_TABLES),
        "repeat_mistake_guard_healthy": has(_GUARD_TABLES),
        "runtime_lease_healthy": has(_EVIDENCE_TABLES),
        "cost_gate_healthy": has(_EVIDENCE_TABLES),
        "no_unresolved_intent": no_unresolved,
    }
