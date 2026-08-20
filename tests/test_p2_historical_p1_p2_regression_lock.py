"""Contract: historical P1→P2 offline regression lock is immutable and CI-gated."""
from __future__ import annotations

from pathlib import Path

from tools.ci.p2_historical_p1_p2_regression_lock import HISTORICAL_P1_P2_REGRESSION_LOCK_MODULES

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "founder_approved_staging_postgres_p2_migration.yml"


def test_historical_lock_modules_exist_and_include_certified_surfaces():
    required_substrings = (
        "test_p1_run8_atomic_recovery",
        "test_p1_closed_at_timestamptz",
        "test_p1_staging_migration_0006",
        "test_bybit_demo_durable_order_foundation",
        "test_p2_run8_learning_closure",
        "test_p2_durable_learning_closure",
        "test_p2_run8_evidence_truth",
        "test_p2_1_postgres_qualification",
        "test_p2_staging_migration_0007",
        "test_p2_migration_atomic",
    )
    joined = "\n".join(HISTORICAL_P1_P2_REGRESSION_LOCK_MODULES)
    for item in required_substrings:
        assert item in joined
    for rel in HISTORICAL_P1_P2_REGRESSION_LOCK_MODULES:
        assert (ROOT / rel).is_file(), rel


def test_workflow_offline_step_runs_historical_regression_lock():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "p2_historical_p1_p2_regression_lock" in source
    assert "HISTORICAL_P1_P2_REGRESSION_LOCK" in source
