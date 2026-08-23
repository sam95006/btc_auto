"""P2 durable learning closure qualification — offline contract and workflow DAG."""
from __future__ import annotations

import json
from pathlib import Path

from tests.test_p2_durable_learning_closure import _durable_run8_intents
from tools.ci.p2_durable_learning_closure_qualification import run

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/founder_approved_staging_postgres_p2_learning_closure_qualification.yml"
MIGRATION_0007 = ROOT / "backend/nexus_persistence_pg/migrations/0007_p2_research_learning_store.sql"


def test_sqlite_full_learning_closure_qualification_passes(tmp_path: Path) -> None:
    evidence = run(intents=_durable_run8_intents(), sqlite_path=tmp_path / "p2_lc_qual.db")
    assert evidence["P2_LEARNING_CLOSURE_QUALIFICATION_PASS"] is True
    assert evidence["RUN8_EXCHANGE_OUTCOME_SOURCE_CONFIRMED"] is True
    assert evidence["REFLECTION_PASS"] is True
    assert evidence["DECISION_OUTCOME_SEPARATION_PASS"] is True
    assert evidence["MISTAKE_CLASSIFICATION_PASS"] is True
    assert evidence["COUNTERFACTUAL_PASS"] is True
    assert evidence["LESSON_CANDIDATE_CREATED"] is True
    assert evidence["P2_LESSON_POSTGRES_WRITE_PASS"] is True
    assert evidence["P2_LESSON_EXACT_READBACK_PASS"] is True
    assert evidence["P2_LESSON_IDEMPOTENCY_PASS"] is True
    assert evidence["POLICY_TRUTH_REMAINS_FALSE"] is True
    assert evidence["REVALIDATION_REQUIRED_TRUE"] is True
    assert evidence["create_order_calls"] == 0
    assert evidence["exchange_write_call_count"] == 0
    assert "run8_certified" not in json.dumps(evidence)


def test_idempotent_replay_does_not_duplicate_lesson(tmp_path: Path) -> None:
    db = tmp_path / "p2_lc_idem.db"
    first = run(intents=_durable_run8_intents(), sqlite_path=db)
    second = run(intents=_durable_run8_intents(), sqlite_path=db)
    assert first["P2_LESSON_IDEMPOTENCY_PASS"] is True
    assert second["P2_LESSON_IDEMPOTENCY_PASS"] is True
    assert first["lesson_id"] == second["lesson_id"]
    assert first["source_evidence_hash"] == second["source_evidence_hash"]


def test_workflow_is_research_only_and_uses_dedicated_runner() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    assert "APPLY_NEXUS_STAGING_P2_LEARNING_CLOSURE_QUALIFICATION" in source
    assert "python -m tools.ci.p2_durable_learning_closure_qualification" in source
    assert "vars.ZEABUR_P2_MIGRATION_CONTROL_SERVICE_ID" in source
    assert "RUN_ONE_BYBIT_DEMO_TRADE" not in source
    assert "ensure_p2_migration_zeabur_service" not in source
    assert "build_p2_zeabur_cli.sh" not in source
    assert 'zeabur deploy --project-id' not in source
    assert "p2_historical_p1_p2_regression_lock" in source
    for flag in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        assert flag in source


def test_workflow_zeabur_cli_before_all_invocations() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    install_idx = source.index("Install official Zeabur CLI and prove prerequisite")
    first_zeabur = min(
        idx for idx in (source.find("zeabur auth"), source.find("zeabur service"), source.find("zeabur variable")) if idx >= 0
    )
    prefix = source[:first_zeabur]
    assert install_idx < first_zeabur
    assert "actions/setup-node@v4" in prefix
    assert "npm install -g zeabur@latest" in prefix
    assert "command -v zeabur" in source
    assert "ZEABUR_CLI_INSTALLED_PASS=true" in source
    cleanup_idx = source.index("Always disarm and clear transient qualification DSN")
    assert install_idx < cleanup_idx


def test_migration_0007_sql_unchanged() -> None:
    sql = MIGRATION_0007.read_text(encoding="utf-8")
    assert "p2_research_lessons" in sql
    assert "source_evidence_hash" in sql
    assert "policy_truth" in sql
    assert "DROP TABLE" not in sql.upper()


def test_p1_certified_surfaces_not_in_workflow() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "founder_approved_bybit_demo_p1_qualification" not in source
    assert "p1_run8_accounting_recovery" not in source
    assert "nexus-bybit-demo-learning-validation" not in source
