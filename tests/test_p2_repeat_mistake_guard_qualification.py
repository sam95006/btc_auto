"""P2 RepeatMistakeGuard behavioral qualification — offline contract and workflow DAG."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.nexus_demo_execution.durable_order_ledger import DurableOrderLedger
from backend.nexus_demo_execution.p2_durable_learning_store import DurableLessonStore
from backend.nexus_demo_execution.p2_run8_durable_loader import load_run8_from_ledger
from backend.nexus_demo_execution.p2_run8_learning_closure import close_run8_durable_learning
from tests.test_p2_durable_learning_closure import _durable_run8_intents
from tools.ci.p2_repeat_mistake_guard_qualification import (
    derive_expected_lesson_identity_from_case,
    run,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/founder_approved_staging_postgres_p2_repeat_mistake_guard_qualification.yml"
MIGRATION_0007 = ROOT / "backend/nexus_persistence_pg/migrations/0007_p2_research_learning_store.sql"


def _seed_lesson(db: Path) -> dict:
    store = DurableLessonStore(sqlite_path=db)
    evidence = close_run8_durable_learning(store=store, intents=_durable_run8_intents())
    store.close()
    return evidence


def _disarm(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        monkeypatch.setenv(key, "false")


def test_a_run8_identity_derived_from_durable_order_ledger() -> None:
    intents = _durable_run8_intents()
    ledger = MagicMock(spec=DurableOrderLedger)
    ledger.list_campaign_intents.return_value = intents
    case = load_run8_from_ledger(ledger)
    expected = derive_expected_lesson_identity_from_case(case)
    assert case["source"] == "DURABLE_POSTGRES_LEDGER"
    assert case["candidate_count"] == 1
    assert expected["lesson_id"] == f"LC_{case['source_evidence_hash'][:24]}"
    assert expected["source_trade_id"] == case["trade_id"]
    assert expected["source_decision_id"] == case["decision_id"]


def test_b_no_latest_row_fallback_uses_evidence_hash_lookup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    db = tmp_path / "p2_rmg_no_latest.db"
    _seed_lesson(db)
    store = DurableLessonStore(sqlite_path=db)
    original_get = store.get_by_evidence_hash
    original_list = store.list_lessons
    list_called = {"value": False}

    def tracked_list() -> list:
        list_called["value"] = True
        return original_list()

    store.get_by_evidence_hash = original_get  # type: ignore[method-assign]
    store.list_lessons = tracked_list  # type: ignore[method-assign]
    store.close()

    source = (ROOT / "tools/ci/p2_repeat_mistake_guard_qualification.py").read_text(encoding="utf-8")
    assert "list_lessons" not in source.split("def run(")[1].split("def main(")[0]
    assert "get_by_evidence_hash" in source
    evidence = run(intents=_durable_run8_intents(), sqlite_path=db)
    assert evidence["DURABLE_LESSON_RETRIEVAL_PASS"] is True
    assert evidence["LATEST_ROW_FALLBACK_FALSE"] is True
    assert list_called["value"] is False


def test_c_multiple_run8_targets_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    dup_intents = _durable_run8_intents() + [_durable_run8_intents()[0].copy()]
    evidence = run(intents=dup_intents, sqlite_path=Path("unused.db"))
    assert evidence["P2_REPEAT_MISTAKE_GUARD_QUALIFICATION_PASS"] is False
    assert "run8_durable_target_not_unique" in str(evidence.get("error"))


def _mutate_lesson_field(db: Path, evidence_hash: str, field: str, value: str) -> None:
    import sqlite3

    conn = sqlite3.connect(str(db))
    conn.execute(
        f"UPDATE p2_research_lessons SET {field}=? WHERE source_evidence_hash=?",
        (value, evidence_hash),
    )
    conn.commit()
    conn.close()


def _delete_lesson(db: Path, evidence_hash: str) -> None:
    import sqlite3

    conn = sqlite3.connect(str(db))
    conn.execute("DELETE FROM p2_research_lessons WHERE source_evidence_hash=?", (evidence_hash,))
    conn.commit()
    conn.close()


@pytest.mark.parametrize(
    ("field", "bad_value", "expected_error"),
    [
        ("lesson_id", "LC_wrong_lesson_id_mismatch", "lesson_id_mismatch_hold"),
        ("source_trade_id", "p1trd_wrong_trade_id", "source_trade_id_mismatch_hold"),
        ("source_decision_id", "p1dec_wrong_decision", "source_decision_id_mismatch_hold"),
    ],
)
def test_d_f_identity_mismatch_holds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    bad_value: str,
    expected_error: str,
) -> None:
    _disarm(monkeypatch)
    db = tmp_path / f"p2_rmg_{field}.db"
    seeded = _seed_lesson(db)
    _mutate_lesson_field(db, seeded["source_evidence_hash"], field, bad_value)
    evidence = run(intents=_durable_run8_intents(), sqlite_path=db)
    assert evidence["P2_REPEAT_MISTAKE_GUARD_QUALIFICATION_PASS"] is False
    assert expected_error in str(evidence.get("error"))


def test_g_wrong_evidence_hash_holds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    db = tmp_path / "p2_rmg_wrong_hash.db"
    seeded = _seed_lesson(db)
    _delete_lesson(db, seeded["source_evidence_hash"])
    evidence = run(intents=_durable_run8_intents(), sqlite_path=db)
    assert evidence["P2_REPEAT_MISTAKE_GUARD_QUALIFICATION_PASS"] is False
    assert "durable_lesson_not_found_hold" in str(evidence.get("error"))


def test_h_workflow_does_not_require_p2_durable_repo_vars() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    for token in (
        "P2_DURABLE_LESSON_ID",
        "P2_DURABLE_LESSON_SOURCE_EVIDENCE_HASH",
        "P2_DURABLE_LESSON_SOURCE_TRADE_ID",
        "P2_DURABLE_LESSON_SOURCE_DECISION_ID",
        "P2_REPEAT_MISTAKE_GUARD_EXPECTED_LESSON_ID",
        "P2_REPEAT_MISTAKE_GUARD_EXPECTED_SOURCE_EVIDENCE_HASH",
        "P2_REPEAT_MISTAKE_GUARD_EXPECTED_SOURCE_TRADE_ID",
        "P2_REPEAT_MISTAKE_GUARD_EXPECTED_SOURCE_DECISION_ID",
    ):
        assert token not in source


def test_sqlite_repeat_mistake_guard_qualification_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    db = tmp_path / "p2_rmg_qual.db"
    _seed_lesson(db)
    evidence = run(intents=_durable_run8_intents(), sqlite_path=db)
    assert evidence["P2_REPEAT_MISTAKE_GUARD_QUALIFICATION_PASS"] is True
    assert evidence["P2_RMG_MANUAL_IDENTITY_DEPENDENCY_REMOVED"] is True
    assert evidence["CERTIFIED_RUN8_DURABLE_IDENTITY_AUTHORITY"] is True
    assert evidence["LESSON_ID_DERIVED_FROM_EVIDENCE_HASH"] is True
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


def test_missing_sqlite_intents_holds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    evidence = run(sqlite_path=tmp_path / "empty.db")
    assert evidence["P2_REPEAT_MISTAKE_GUARD_QUALIFICATION_PASS"] is False
    assert "sqlite_intents_required_hold" in str(evidence.get("error"))


def test_deterministic_replay_same_outcome(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    db = tmp_path / "p2_rmg_det.db"
    _seed_lesson(db)
    first = run(intents=_durable_run8_intents(), sqlite_path=db)
    second = run(intents=_durable_run8_intents(), sqlite_path=db)
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
