from __future__ import annotations

from pathlib import Path

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
