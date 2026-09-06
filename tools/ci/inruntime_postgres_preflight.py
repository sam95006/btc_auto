#!/usr/bin/env python3
"""IN-RUNTIME read-only Postgres preflight for the bounded-Demo control plane.

Runs INSIDE the validation service (nexus-bybit-demo-learning-validation) via
`zeabur service exec`, using the service's OWN runtime NEXUS_POSTGRES_URL over the
Zeabur private network. The GitHub Actions runner therefore never needs the
Postgres DSN and the PostgreSQL Public Port stays OFF.

Read-only; no mutation. Prints ONLY sanitized PASS/FAIL markers — never the DSN,
username, password, host, or any credential. Fails closed on any missing/
unreadable/unresolved condition.
"""
from __future__ import annotations

import os
import sys

# The sanitized boolean markers the control plane consumes (order = stable output).
MARKER_KEYS = (
    "POSTGRES_AVAILABLE",
    "MIGRATION_0007_PRESENT",
    "DURABLE_LESSONS_READABLE",
    "DURABLE_ORDER_LEDGER_READABLE",
    "NO_UNRESOLVED_ORPHAN_INTENTS",
    "NO_UNKNOWN_OUTCOME_STATE",
    "STARTUP_RECONCILIATION_ENTRIES_ALLOWED",
)


def to_markers(pg: dict) -> dict[str, bool]:
    """Map the raw (never-printed) _postgres_preflight result to sanitized booleans.
    Raw counts / DSN are NEVER surfaced — only pass/fail booleans."""
    available = pg.get("postgres_available") is True
    ledger_readable = available and "error" not in pg
    return {
        "POSTGRES_AVAILABLE": available,
        "MIGRATION_0007_PRESENT": pg.get("migration_0007_present") is True,
        "DURABLE_LESSONS_READABLE": pg.get("durable_lessons_readable") is True,
        "DURABLE_ORDER_LEDGER_READABLE": ledger_readable,
        "NO_UNRESOLVED_ORPHAN_INTENTS": int(pg.get("unresolved_intent_count") or 0) == 0
        and int(pg.get("orphan_positions") or 0) == 0,
        "NO_UNKNOWN_OUTCOME_STATE": int(pg.get("unknown_outcome_count") or 0) == 0,
        "STARTUP_RECONCILIATION_ENTRIES_ALLOWED": pg.get("entries_allowed") is True,
    }


def all_pass(markers: dict[str, bool]) -> bool:
    return all(markers.get(key) is True for key in MARKER_KEYS)


def _emit(markers: dict[str, bool]) -> None:
    for key in MARKER_KEYS:
        print(f"{key}={'true' if markers.get(key) else 'false'}")


def main() -> int:
    # Runtime DSN comes ONLY from the service's own environment; never a runner
    # value, never a public DSN. Missing -> fail closed (do not inject anything).
    dsn = (os.environ.get("NEXUS_POSTGRES_URL") or "").strip()
    if not dsn:
        print("VALIDATION_RUNTIME_POSTGRES_MISSING=true")
        print("INRUNTIME_POSTGRES_PREFLIGHT_PASS=false")
        return 1

    # Reuse the single canonical read-only DB-proof routine. Its result (which
    # holds no DSN) is converted to sanitized booleans and never printed raw.
    from tools.ci.demo_bounded_session_preflight import _postgres_preflight

    markers = to_markers(_postgres_preflight(dsn))
    _emit(markers)
    ok = all_pass(markers)
    print(f"INRUNTIME_POSTGRES_PREFLIGHT_PASS={'true' if ok else 'false'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
