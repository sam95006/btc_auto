from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import tools.ci.p1_staging_migration_0006 as migration
from tools.ci.p1_staging_migration_0006 import EXPECTED_PENDING, REQUIRED_COLUMNS


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "founder_approved_staging_postgres_p1_migration.yml"
HELPER = ROOT / "tools" / "ci" / "p1_staging_migration_0006.py"


def test_migration_0006_guard_has_only_the_expected_pending_version() -> None:
    assert EXPECTED_PENDING == ["0006"]
    assert REQUIRED_COLUMNS == {
        "parent_order_intent_id",
        "actual_entry_price",
        "actual_exit_price",
        "realized_demo_pnl",
        "wallet_delta",
        "closed_at",
        "pnl_provenance",
        "accounting_json",
    }


def test_migration_guard_uses_runner_cli_and_rejects_unexpected_state() -> None:
    source = HELPER.read_text(encoding="utf-8")
    assert "MigrationRunner()" in source
    assert '"backend.nexus_persistence_pg.cli", "migrate", "apply"' in source
    assert "--allow-destructive" not in source
    assert 'before["pending_versions"] != EXPECTED_PENDING' in source
    assert "runner.detect_drift(pool)" in source
    assert "ALTER TABLE" not in source


def test_migration_workflow_is_dispatch_only_and_disarmed() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    assert "APPLY_NEXUS_STAGING_P1_MIGRATION_0006" in source
    assert "python tools/ci/p1_staging_migration_0006.py" in source
    assert "backend.nexus_persistence_pg.cli" not in source  # helper exclusively owns runner invocation
    assert "MAINNET false" in source
    assert "REAL_MONEY false" in source
    assert "DEMO_AUTONOMOUS_ENABLED false" in source
    assert "AUTONOMOUS_SEND false" in source
    assert "EXCHANGE_WRITE false" in source
    assert "NEXUS_POSTGRES_URL" in source
    assert "zeabur variable delete" in source


class _PostVerifyPool:
    def __init__(self, columns: set[str], *, index_exists: bool = True) -> None:
        self.columns = columns
        self.index_exists = index_exists

    def fetchall(self, statement: str):
        assert "information_schema.columns" in statement
        return [(column,) for column in self.columns]

    def fetchval(self, statement: str):
        assert "pg_indexes" in statement
        return self.index_exists


def test_post_verify_reports_exact_required_columns(monkeypatch) -> None:
    monkeypatch.setattr(
        migration,
        "_state",
        lambda _pool: {
            "migration_catalog_valid": True,
            "checksum_drift": [],
            "applied_versions": ["0001", "0002", "0003", "0004", "0005", "0006"],
            "pending_versions": [],
            "order_intent_count": 0,
            "order_history_count": 0,
        },
    )
    verified = migration._post_verify(_PostVerifyPool(set(REQUIRED_COLUMNS)))  # type: ignore[arg-type]
    assert verified["required_columns_present"] == sorted(REQUIRED_COLUMNS)
    assert verified["missing_columns"] == []
    assert verified["parent_index_present"] is True


def test_post_verify_reports_missing_required_column_without_type_error(monkeypatch) -> None:
    monkeypatch.setattr(migration, "_state", lambda _pool: {})
    missing = "wallet_delta"
    verified = migration._post_verify(_PostVerifyPool(set(REQUIRED_COLUMNS) - {missing}))  # type: ignore[arg-type]
    assert verified["required_columns_present"] == sorted(REQUIRED_COLUMNS - {missing})
    assert verified["missing_columns"] == [missing]


class _RunPool:
    def __init__(self, _url: str) -> None:
        self.closed = False

    def open(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def _migration_state(versions: list[str]) -> dict:
    return {
        "migration_catalog_valid": True,
        "migration_catalog_errors": [],
        "applied_versions": versions,
        "pending_versions": ["0006"] if "0006" not in versions else [],
        "checksum_drift": [],
        "order_intent_count": 0,
        "order_history_count": 0,
    }


def test_run_passes_only_after_exact_apply_and_post_verify(monkeypatch) -> None:
    states = iter([_migration_state(["0001", "0002", "0003", "0004", "0005"])])
    monkeypatch.setenv("NEXUS_POSTGRES_URL", "postgresql://not-used-in-test")
    monkeypatch.setattr(migration, "PostgresPool", _RunPool)
    monkeypatch.setattr(migration, "_state", lambda _pool: next(states))
    monkeypatch.setattr(
        migration,
        "_post_verify",
        lambda _pool: {
            **_migration_state(["0001", "0002", "0003", "0004", "0005", "0006"]),
            "required_columns_present": sorted(REQUIRED_COLUMNS),
            "missing_columns": [],
            "parent_index_present": True,
        },
    )
    monkeypatch.setattr(
        migration.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout=json.dumps({"ok": True, "applied": ["0006"], "errors": []})
        ),
    )
    evidence = migration.run()
    assert evidence["P1_MIGRATION_0006_APPLIED_PASS"] is True
    assert evidence["error"] is None


def test_run_fails_closed_when_post_verify_is_incomplete(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_POSTGRES_URL", "postgresql://not-used-in-test")
    monkeypatch.setattr(migration, "PostgresPool", _RunPool)
    monkeypatch.setattr(migration, "_state", lambda _pool: _migration_state(["0001", "0002", "0003", "0004", "0005"]))
    monkeypatch.setattr(
        migration,
        "_post_verify",
        lambda _pool: {
            **_migration_state(["0001", "0002", "0003", "0004", "0005", "0006"]),
            "required_columns_present": sorted(REQUIRED_COLUMNS - {"wallet_delta"}),
            "missing_columns": ["wallet_delta"],
            "parent_index_present": True,
        },
    )
    monkeypatch.setattr(
        migration.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout=json.dumps({"ok": True, "applied": ["0006"], "errors": []})
        ),
    )
    evidence = migration.run()
    assert evidence["P1_MIGRATION_0006_APPLIED_PASS"] is False
    assert evidence["error"] == "post_migration_verification_failed"
