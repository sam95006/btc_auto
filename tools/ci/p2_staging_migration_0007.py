#!/usr/bin/env python3
"""Founder-gated, schema-only qualification for staging P2 migration 0007."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from backend.nexus_persistence_pg.migrate import MigrationRunner
from backend.nexus_persistence_pg.pool import PostgresPool


EXPECTED_PENDING = ["0007"]
REQUIRED_PRIOR = ["0001", "0002", "0003", "0004", "0005", "0006"]


def _write_evidence(payload: dict[str, Any]) -> None:
    path = Path(os.environ.get("P2_MIGRATION_EVIDENCE_PATH") or "/tmp/nexus_demo_validation/p2_migration_0007.json")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def _state(pool: PostgresPool) -> dict[str, Any]:
    runner = MigrationRunner()
    validation = runner.validate()
    catalog_versions = {item["version"] for item in validation["catalog"]["migrations"]}
    applied = sorted(runner.applied_versions(pool))
    pending = sorted(catalog_versions - set(applied))
    drift = runner.detect_drift(pool)
    intent_count = int(pool.fetchval("SELECT COUNT(*) FROM nexus.bybit_demo_order_intents") or 0)
    history_count = int(pool.fetchval("SELECT COUNT(*) FROM nexus.bybit_demo_order_state_history") or 0)
    return {
        "migration_catalog_valid": bool(validation["ok"]),
        "migration_catalog_errors": list(validation["errors"]),
        "applied_versions": applied,
        "pending_versions": pending,
        "checksum_drift": drift,
        "order_intent_count": intent_count,
        "order_history_count": history_count,
    }


def _post_verify(pool: PostgresPool) -> dict[str, Any]:
    state = _state(pool)
    table_exists = bool(
        pool.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='nexus' AND table_name='p2_research_lessons'
            )
            """
        )
    )
    constraints = {
        str(row[0]): str(row[1])
        for row in pool.fetchall(
            """
            SELECT conname, pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_class t ON t.oid=c.conrelid
            JOIN pg_namespace n ON n.oid=t.relnamespace
            WHERE n.nspname='nexus' AND t.relname='p2_research_lessons'
            """
        )
    }
    unique_hash = any(
        "UNIQUE" in definition.upper() and "source_evidence_hash" in definition
        for definition in constraints.values()
    )
    policy_support = any(
        "policy_truth" in definition and "support_count" in definition
        for definition in constraints.values()
    )
    lesson_count = 0
    if table_exists:
        lesson_count = int(pool.fetchval("SELECT COUNT(*) FROM nexus.p2_research_lessons") or 0)
    state.update(
        {
            "p2_research_lessons_present": table_exists,
            "source_evidence_hash_unique": unique_hash,
            "policy_truth_support_constraint": policy_support,
            "lesson_count": lesson_count,
            "constraint_names": sorted(constraints),
        }
    )
    return state


def run() -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "P2_MIGRATION_0007_APPLIED_PASS": False,
        "exchange_write_call_count": 0,
        "create_order_calls": 0,
        "error": None,
    }
    database_url = (os.environ.get("NEXUS_POSTGRES_URL") or "").strip()
    if not database_url:
        evidence["error"] = "postgres_url_missing"
        return evidence
    pool = PostgresPool(database_url)
    try:
        pool.open()
        before = _state(pool)
        evidence["pre_migration"] = before
        _write_evidence(evidence)
        if (
            not before["migration_catalog_valid"]
            or before["checksum_drift"]
            or before["pending_versions"] != EXPECTED_PENDING
            or any(version not in before["applied_versions"] for version in REQUIRED_PRIOR)
        ):
            evidence["error"] = "pre_migration_state_not_exactly_0007"
            return evidence

        apply = subprocess.run(
            [sys.executable, "-m", "backend.nexus_persistence_pg.cli", "migrate", "apply"],
            capture_output=True,
            text=True,
            check=False,
            env=os.environ.copy(),
        )
        try:
            apply_result = json.loads(apply.stdout)
        except json.JSONDecodeError:
            evidence["error"] = "migration_runner_output_malformed"
            return evidence
        evidence["apply"] = {
            "exit_code": apply.returncode,
            "ok": bool(apply_result.get("ok")),
            "applied": list(apply_result.get("applied") or []),
            "errors": list(apply_result.get("errors") or []),
        }
        if apply.returncode != 0 or apply_result.get("applied") != EXPECTED_PENDING or not apply_result.get("ok"):
            evidence["error"] = "migration_apply_not_exactly_0007"
            return evidence

        after = _post_verify(pool)
        evidence["post_migration"] = after
        counts_unchanged = (
            after["order_intent_count"] == before["order_intent_count"]
            and after["order_history_count"] == before["order_history_count"]
        )
        evidence["P2_MIGRATION_0007_APPLIED_PASS"] = bool(
            after["migration_catalog_valid"]
            and not after["checksum_drift"]
            and all(version in after["applied_versions"] for version in [*REQUIRED_PRIOR, "0007"])
            and after["p2_research_lessons_present"]
            and after["source_evidence_hash_unique"]
            and after["policy_truth_support_constraint"]
            and counts_unchanged
        )
        if not evidence["P2_MIGRATION_0007_APPLIED_PASS"]:
            evidence["error"] = "post_migration_verification_failed"
        return evidence
    except Exception as exc:  # noqa: BLE001
        evidence["error"] = f"migration_qualification_error:{type(exc).__name__}"
        return evidence
    finally:
        pool.close()


def main() -> int:
    try:
        evidence = run()
    except Exception as exc:  # noqa: BLE001
        evidence = {
            "P2_MIGRATION_0007_APPLIED_PASS": False,
            "exchange_write_call_count": 0,
            "create_order_calls": 0,
            "error": f"migration_unhandled_error:{type(exc).__name__}",
        }
    _write_evidence(evidence)
    print(json.dumps(evidence, sort_keys=True))
    return 0 if evidence["P2_MIGRATION_0007_APPLIED_PASS"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
