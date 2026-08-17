from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.ci.p1_staging_migration_0006 as migration
from tools.ci.p1_staging_migration_0006 import EXPECTED_PENDING, REQUIRED_COLUMNS
from tools.ci.p1_parse_migration_stdout import parse_migration_stdout


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
    assert "p1_migration_transport_probe_${GITHUB_RUN_ID}_${GITHUB_RUN_ATTEMPT}.txt" in source
    assert "P1_MIGRATION_TRANSPORT_${GITHUB_RUN_ID}_${GITHUB_RUN_ATTEMPT}" in source
    assert "P1_MIGRATION_SERVICE_EXEC_FILE_CHANNEL_PASS=true" in source
    assert source.index("P1_MIGRATION_SERVICE_EXEC_FILE_CHANNEL_PASS=true") < source.index(
        "python tools/ci/p1_staging_migration_0006.py"
    )
    assert "p1_parse_migration_stdout.py" in source


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


def test_unexpected_pending_migration_blocks_apply_before_subprocess(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_POSTGRES_URL", "postgresql://not-used-in-test")
    monkeypatch.setattr(migration, "PostgresPool", _RunPool)
    state = _migration_state(["0001", "0002", "0003", "0004", "0005"])
    state["pending_versions"] = ["0006", "0007"]
    monkeypatch.setattr(migration, "_state", lambda _pool: state)
    monkeypatch.setattr(
        migration.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("MigrationRunner must not execute for an unexpected pending migration"),
    )
    evidence = migration.run()
    assert evidence["error"] == "pre_migration_state_not_exactly_0006"
    assert evidence["pre_migration"]["applied_versions"] == ["0001", "0002", "0003", "0004", "0005"]


def test_main_writes_sanitized_evidence_for_unhandled_exception(monkeypatch, tmp_path, capsys) -> None:
    evidence_path = tmp_path / "migration_evidence.json"
    monkeypatch.setenv("P1_MIGRATION_EVIDENCE_PATH", str(evidence_path))
    monkeypatch.setattr(migration, "run", lambda: (_ for _ in ()).throw(RuntimeError("postgres://sensitive")))
    assert migration.main() == 1
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload == {
        "P1_MIGRATION_0006_APPLIED_PASS": False,
        "exchange_write_call_count": 0,
        "create_order_calls": 0,
        "error": "migration_unhandled_error:RuntimeError",
    }
    assert "postgres://sensitive" not in capsys.readouterr().out


def test_migration_stdout_diagnostic_is_allowlisted_only() -> None:
    raw = json.dumps(
        {
            "P1_MIGRATION_0006_APPLIED_PASS": False,
            "error": "postgres://secret",
            "pre_migration": {"applied_versions": ["0001"], "pending_versions": ["0006"], "checksum_drift": []},
            "apply": {"exit_code": 1, "ok": False, "applied": []},
            "post_migration": {"applied_versions": [], "missing_columns": ["wallet_delta"], "parent_index_present": False},
        }
    )
    diagnostic = parse_migration_stdout(f"transport prefix {raw}")
    assert diagnostic["migration_runner_json_detected"] is True
    assert diagnostic["migration_runner_error"] == "redacted"
    assert diagnostic["migration_pre_pending_versions"] == ["0006"]
    assert "NEXUS_POSTGRES_URL" not in diagnostic


def test_migration_stdout_traceback_reports_exception_type_only() -> None:
    diagnostic = parse_migration_stdout("Traceback (most recent call last):\nRuntimeError: sensitive details\n")
    assert diagnostic == {"migration_runner_json_detected": False, "migration_exception_type": "RuntimeError"}
