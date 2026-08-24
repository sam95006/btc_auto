"""P2 RepeatMistakeGuard behavioral qualification — offline contract and workflow DAG."""
from __future__ import annotations

import json
import os
from pathlib import Path

from backend.nexus_demo_execution.p2_durable_learning_store import DurableLessonStore
from backend.nexus_demo_execution.p2_run8_learning_closure import close_run8_durable_learning
from tests.test_p2_durable_learning_closure import _durable_run8_intents
from tools.ci.p2_repeat_mistake_guard_qualification import run

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/founder_approved_staging_postgres_p2_repeat_mistake_guard_qualification.yml"
MIGRATION_0007 = ROOT / "backend/nexus_persistence_pg/migrations/0007_p2_research_learning_store.sql"


def _seed_lesson_and_env(db: Path) -> None:
    store = DurableLessonStore(sqlite_path=db)
    evidence = close_run8_durable_learning(store=store, intents=_durable_run8_intents())
    store.close()
    os.environ["P2_REPEAT_MISTAKE_GUARD_EXPECTED_LESSON_ID"] = evidence["lesson_id"]
    os.environ["P2_REPEAT_MISTAKE_GUARD_EXPECTED_SOURCE_EVIDENCE_HASH"] = evidence["source_evidence_hash"]
    os.environ["P2_REPEAT_MISTAKE_GUARD_EXPECTED_SOURCE_TRADE_ID"] = evidence["trade_id"]
    os.environ["P2_REPEAT_MISTAKE_GUARD_EXPECTED_SOURCE_DECISION_ID"] = evidence["decision_id"]


def test_sqlite_repeat_mistake_guard_qualification_passes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MAINNET", "false")
    monkeypatch.setenv("REAL_MONEY", "false")
    monkeypatch.setenv("EXCHANGE_WRITE", "false")
    monkeypatch.setenv("DEMO_AUTONOMOUS_ENABLED", "false")
    monkeypatch.setenv("AUTONOMOUS_SEND", "false")
    db = tmp_path / "p2_rmg_qual.db"
    _seed_lesson_and_env(db)
    evidence = run(sqlite_path=db)
    assert evidence["P2_REPEAT_MISTAKE_GUARD_QUALIFICATION_PASS"] is True
    assert evidence["DURABLE_LESSON_RETRIEVAL_PASS"] is True
    assert evidence["SIMILARITY_ENGINE_PASS"] is True
    assert evidence["SIMILAR_CANDIDATE_MATCH_PASS"] is True
    assert evidence["DISSIMILAR_CONTROL_REJECT_PASS"] is True
    assert evidence["PRE_POST_BEHAVIOR_DIFFERENCE_PASS"] is True
    assert evidence["REPEAT_MISTAKE_GUARD_EFFECT_PASS"] is True
    assert evidence["P2_REPEAT_MISTAKE_GUARD_DETERMINISM_PASS"] is True
    assert evidence["HARD_RISK_AUTHORITY_UNCHANGED"] is True
    assert evidence["LESSON_POLICY_TRUTH_REMAINS_FALSE"] is True
    assert evidence["LESSON_REVALIDATION_REQUIRED_TRUE"] is True
    assert evidence["PRE_GUARD_DECISION"] == "ALLOW"
    assert evidence["POST_GUARD_DECISION"] == "SKIP"
    assert evidence["create_order_calls"] == 0
    assert evidence["exchange_write_call_count"] == 0
    assert "run8_certified" not in json.dumps(evidence)


def test_missing_expected_identity_holds(tmp_path: Path, monkeypatch) -> None:
    for key in (
        "P2_REPEAT_MISTAKE_GUARD_EXPECTED_LESSON_ID",
        "P2_REPEAT_MISTAKE_GUARD_EXPECTED_SOURCE_EVIDENCE_HASH",
        "P2_REPEAT_MISTAKE_GUARD_EXPECTED_SOURCE_TRADE_ID",
        "P2_REPEAT_MISTAKE_GUARD_EXPECTED_SOURCE_DECISION_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    evidence = run(sqlite_path=tmp_path / "empty.db")
    assert evidence["P2_REPEAT_MISTAKE_GUARD_QUALIFICATION_PASS"] is False
    assert "expected_lesson_identity_missing_hold" in str(evidence.get("error"))


def test_deterministic_replay_same_outcome(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MAINNET", "false")
    monkeypatch.setenv("REAL_MONEY", "false")
    monkeypatch.setenv("EXCHANGE_WRITE", "false")
    monkeypatch.setenv("DEMO_AUTONOMOUS_ENABLED", "false")
    monkeypatch.setenv("AUTONOMOUS_SEND", "false")
    db = tmp_path / "p2_rmg_det.db"
    _seed_lesson_and_env(db)
    first = run(sqlite_path=db)
    second = run(sqlite_path=db)
    assert first["P2_REPEAT_MISTAKE_GUARD_DETERMINISM_PASS"] is True
    assert first["SIMILARITY_SCORE"] == second["SIMILARITY_SCORE"]
    assert first["POST_GUARD_DECISION"] == second["POST_GUARD_DECISION"]


def test_workflow_is_research_only_and_uses_dedicated_runner() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    assert "QUALIFY_NEXUS_STAGING_P2_REPEAT_MISTAKE_GUARD" in source
    assert "python -m tools.ci.p2_repeat_mistake_guard_qualification" in source
    assert "vars.ZEABUR_P2_MIGRATION_CONTROL_SERVICE_ID" in source
    assert "ensure_p2_migration_zeabur_service" not in source
    assert "close_run8_durable_learning" not in source
    assert "RUN_ONE_BYBIT_DEMO_TRADE" not in source
    assert "p2_historical_p1_p2_regression_lock" in source


def test_workflow_zeabur_cli_before_service_exec() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    install_idx = source.index("Install official Zeabur CLI and prove prerequisite")
    first_zeabur = min(
        idx for idx in (source.find("zeabur auth"), source.find("zeabur service"), source.find("zeabur variable")) if idx >= 0
    )
    assert install_idx < first_zeabur
    assert "npm install -g zeabur@latest" in source


def test_migration_0007_sql_unchanged() -> None:
    sql = MIGRATION_0007.read_text(encoding="utf-8")
    assert "p2_research_lessons" in sql
    assert "DROP TABLE" not in sql.upper()
