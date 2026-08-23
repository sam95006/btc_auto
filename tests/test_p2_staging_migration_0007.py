from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.ci.p2_staging_migration_0007 as migration
from tools.ci.p2_parse_migration_stdout import parse_migration_stdout
from tools.ci.p2_staging_migration_0007 import EXPECTED_PENDING, REQUIRED_PRIOR
from backend.nexus_persistence_pg.migrate import MigrationRunner, list_migrations


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "founder_approved_staging_postgres_p2_migration.yml"
HELPER = ROOT / "tools" / "ci" / "p2_staging_migration_0007.py"


def test_migration_0007_guard_has_only_the_expected_pending_version() -> None:
    assert EXPECTED_PENDING == ["0007"]
    assert REQUIRED_PRIOR == ["0001", "0002", "0003", "0004", "0005", "0006"]


def test_migration_0007_is_forward_only() -> None:
    files = {item.version: item for item in list_migrations()}
    assert "0007" in files
    assert "DROP TABLE" not in files["0007"].sql.upper()
    assert "p2_research_lessons" in files["0007"].sql
    assert "source_evidence_hash" in files["0007"].sql
    assert MigrationRunner().validate()["ok"] is True


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
    assert "APPLY_NEXUS_STAGING_P2_MIGRATION_0007" in source
    assert "nexus-p2m7-${{ github.run_id }}-${{ github.run_attempt }}" in source
    assert "P2_MIGRATION_RUN_SCOPED_SERVICE=true" in source
    assert "P2_MIGRATION_SINGLE_DEPLOY_BOOTSTRAP=true" in source
    assert "P2_MIGRATION_PREVIOUS_SERVICE_REUSED=false" in source
    assert 'SERVICE_NAME: nexus-p2-migration-0007' not in source
    assert "python -m tools.ci.ensure_p2_migration_zeabur_service" in source
    assert "Build migration deployment context before service create" in source
    assert "P2_MIGRATION_SECOND_SERVICE_CREATED=false" in source
    assert "zeabur deploy --project-id \"$ZEABUR_PROJECT_ID\" --service-id \"$SERVICE_ID\"" not in source
    assert "python tools/ci/ensure_p2_migration_zeabur_service.py" not in source
    assert "p2_migration_atomic.py --print-remote-script" in source
    assert "python -m tools.ci.p2_extract_migration_authoritative_stdout" in source
    assert "python -m tools.ci.p2_migration_parse_service_exec" in source
    assert "P2_MIGRATION_DEPLOYMENT_CONVERGED=true" in source
    assert "Require migration helper imports before apply" not in source
    assert "Apply and verify only migration 0007 through atomic same-exec" in source
    assert "file_channel_authoritative=false" in source
    assert "MAINNET false" in source
    assert "REAL_MONEY false" in source
    assert "DEMO_AUTONOMOUS_ENABLED false" in source
    assert "AUTONOMOUS_SEND false" in source
    assert "EXCHANGE_WRITE false" in source
    assert "NEXUS_POSTGRES_URL" in source
    assert "zeabur variable delete" in source
    assert "p2_parse_migration_stdout.py" in source
    assert "p1_qualification" not in source
    assert "RUN_ONE_BYBIT_DEMO_TRADE" not in source
    assert "nexus-bybit-demo-learning-validation" not in source
    assert "P2_MIGRATION_SERVICE_EXEC_STDOUT_PASS=true" in source
    assert "P2_MIGRATION_FILE_CHANNEL_AUDIT=true" in source
    assert "P2_MIGRATION_OPERATIONAL_READINESS_PASS=true" in source
    assert "not_running_count=" in source
    assert "bootstrap_positive_proof_count=" in source or "activation_positive_proof_count=" in source
    assert "p2_historical_p1_p2_regression_lock" in source
    assert "Metadata diagnostic audit-only" in source
    assert "Activation operational readiness before migration" in source
    assert "Bootstrap operational readiness before runtime variables" in source
    assert "p2_migration_deployment_diagnostics" in source
    assert "P2_MIGRATION_OPERATIONAL_READINESS_PASS=true" in source
    assert source.index("Bootstrap operational readiness before runtime variables") < source.index(
        "Activation operational readiness before migration"
    )

class _PostVerifyPool:
    def fetchall(self, statement: str):
        assert "pg_constraint" in statement
        return [
            ("p2_research_lessons_source_hash_uk", "UNIQUE (source_evidence_hash)"),
            (
                "p2_research_lessons_policy_truth_chk",
                "CHECK ((policy_truth = FALSE) OR (support_count >= 3))",
            ),
        ]

    def fetchval(self, statement: str):
        if "information_schema.tables" in statement:
            return True
        if "COUNT(*)" in statement:
            return 0
        return False


def test_post_verify_reports_lesson_table_and_constraints(monkeypatch) -> None:
    monkeypatch.setattr(
        migration,
        "_state",
        lambda _pool: {
            "migration_catalog_valid": True,
            "checksum_drift": [],
            "applied_versions": ["0001", "0002", "0003", "0004", "0005", "0006", "0007"],
            "pending_versions": [],
            "order_intent_count": 2,
            "order_history_count": 4,
        },
    )
    verified = migration._post_verify(_PostVerifyPool())  # type: ignore[arg-type]
    assert verified["p2_research_lessons_present"] is True
    assert verified["source_evidence_hash_unique"] is True
    assert verified["policy_truth_support_constraint"] is True


class _RunPool:
    def __init__(self, _url: str) -> None:
        self.closed = False

    def open(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def _migration_state(versions: list[str]) -> dict:
    pending = ["0007"] if "0007" not in versions else []
    return {
        "migration_catalog_valid": True,
        "migration_catalog_errors": [],
        "applied_versions": versions,
        "pending_versions": pending,
        "checksum_drift": [],
        "order_intent_count": 0,
        "order_history_count": 0,
    }


def test_run_passes_only_after_exact_apply_and_post_verify(monkeypatch) -> None:
    states = iter([_migration_state(["0001", "0002", "0003", "0004", "0005", "0006"])])
    monkeypatch.setenv("NEXUS_POSTGRES_URL", "postgresql://not-used-in-test")
    monkeypatch.setattr(migration, "PostgresPool", _RunPool)
    monkeypatch.setattr(migration, "_state", lambda _pool: next(states))
    monkeypatch.setattr(
        migration,
        "_post_verify",
        lambda _pool: {
            **_migration_state(["0001", "0002", "0003", "0004", "0005", "0006", "0007"]),
            "p2_research_lessons_present": True,
            "source_evidence_hash_unique": True,
            "policy_truth_support_constraint": True,
        },
    )
    monkeypatch.setattr(
        migration.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout=json.dumps({"ok": True, "applied": ["0007"], "errors": []})
        ),
    )
    evidence = migration.run()
    assert evidence["P2_MIGRATION_0007_APPLIED_PASS"] is True
    assert evidence["error"] is None


def test_run_fails_closed_when_0006_is_still_pending(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_POSTGRES_URL", "postgresql://not-used-in-test")
    monkeypatch.setattr(migration, "PostgresPool", _RunPool)
    state = _migration_state(["0001", "0002", "0003", "0004", "0005"])
    state["pending_versions"] = ["0006", "0007"]
    monkeypatch.setattr(migration, "_state", lambda _pool: state)
    monkeypatch.setattr(
        migration.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("MigrationRunner must not execute unless pending is exactly 0007"),
    )
    evidence = migration.run()
    assert evidence["error"] == "pre_migration_state_not_exactly_0007"
    assert evidence["P2_MIGRATION_0007_APPLIED_PASS"] is False


def test_migration_stdout_diagnostic_is_allowlisted_only() -> None:
    raw = json.dumps(
        {
            "P2_MIGRATION_0007_APPLIED_PASS": False,
            "error": "postgres://secret",
            "pre_migration": {"applied_versions": ["0006"], "pending_versions": ["0007"], "checksum_drift": []},
            "apply": {"exit_code": 1, "ok": False, "applied": []},
            "post_migration": {"applied_versions": [], "p2_research_lessons_present": False},
        }
    )
    diagnostic = parse_migration_stdout(f"transport prefix {raw}")
    assert diagnostic["migration_runner_json_detected"] is True
    assert diagnostic["migration_runner_error"] == "redacted"
    assert diagnostic["migration_pre_pending_versions"] == ["0007"]


def test_helper_module_executes_from_app_import_root_without_db_access() -> None:
    import subprocess
    import sys

    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    env.pop("NEXUS_POSTGRES_URL", None)
    result = subprocess.run(
        [sys.executable, "-m", "tools.ci.p2_staging_migration_0007"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    evidence = json.loads(result.stdout)
    assert evidence["error"] == "postgres_url_missing"
    assert evidence["exchange_write_call_count"] == 0
    assert evidence["create_order_calls"] == 0
