"""Offline P2.1 postgres qualification helper tests. No exchange writes."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from backend.nexus_demo_execution.p2_durable_learning_store import DurableLessonStore
from backend.nexus_demo_execution.p2_run8_learning_closure import close_run8_durable_learning
from tests.test_p2_durable_learning_closure import _durable_run8_intents
from tools.ci.p2_1_postgres_qualification import process_b_prewrite_read, run


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "founder_approved_staging_postgres_p2_1_qualification.yml"


def test_qualification_workflow_is_research_only() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    assert "APPLY_NEXUS_STAGING_P2_1_POSTGRES_QUALIFICATION" in source
    assert "python -m tools.ci.p2_1_postgres_qualification" in source
    assert "p2_parse_qualification_stdout.py" in source
    assert "RUN_ONE_BYBIT_DEMO_TRADE" not in source
    assert "p1_run8_accounting_recovery" not in source
    assert "EXCHANGE_WRITE false" in source


def test_sqlite_restart_durability_idempotency_and_unrelated_context(tmp_path: Path) -> None:
    evidence = run(intents=_durable_run8_intents(), sqlite_path=tmp_path / "p2_qual.db")
    assert evidence["POSTGRES_LESSON_PERSISTED"] is True
    assert evidence["PROCESS_B_PREWRITE_LESSON_FOUND"] is True
    assert evidence["PROCESS_B_PREWRITE_MEMORY_HIT"] is True
    assert evidence["PROCESS_B_WRITES_BEFORE_MEMORY_CHECK"] == 0
    assert evidence["POSTGRES_MEMORY_SURVIVES_NEW_PROCESS"] is True
    assert evidence["DUPLICATE_LESSON_COUNT"] == 1
    assert evidence["DUPLICATE_LESSON_IDEMPOTENCY_PASS"] is True
    assert evidence["IDEMPOTENCY_SEPARATED_FROM_DURABILITY"] is True
    assert evidence["POLICY_TRUTH"] is False
    assert evidence["SUPPORT_COUNT"] == 1
    assert evidence["research_recommendation_after"] == "RESEARCH_SKIP"
    assert evidence["unrelated_research_recommendation"] == "RESEARCH_ALLOW"
    assert evidence["create_order_calls"] == 0
    assert evidence["exchange_write_call_count"] == 0
    assert evidence["AUTONOMOUS_BYBIT_DEMO_ARM_READY"] == "HOLD"
    assert evidence["P2_1_POSTGRES_QUALIFICATION_PASS"] is True
    assert "run8_certified" not in json.dumps(evidence)


def test_process_b_finds_lesson_without_any_write(tmp_path: Path) -> None:
    db = tmp_path / "p2_prewrite.db"
    intents = _durable_run8_intents()
    store_a = DurableLessonStore(sqlite_path=db)
    process_a = close_run8_durable_learning(store=store_a, intents=intents)
    store_a.close()
    store_b = DurableLessonStore(sqlite_path=db)
    result = process_b_prewrite_read(store_b, process_a=process_a)
    store_b.close()
    assert result["PROCESS_B_PREWRITE_LESSON_FOUND"] is True
    assert result["PROCESS_B_PREWRITE_MEMORY_HIT"] is True
    assert result["PROCESS_B_WRITES_BEFORE_MEMORY_CHECK"] == 0
    assert result["POSTGRES_MEMORY_SURVIVES_NEW_PROCESS"] is True


def test_missing_persisted_lesson_fails_process_b(tmp_path: Path) -> None:
    db = tmp_path / "p2_missing.db"
    intents = _durable_run8_intents()
    store_a = DurableLessonStore(sqlite_path=db)
    process_a = close_run8_durable_learning(store=store_a, intents=intents)
    store_a.close()
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM p2_research_lessons")
    conn.commit()
    conn.close()
    store_b = DurableLessonStore(sqlite_path=db)
    result = process_b_prewrite_read(store_b, process_a=process_a)
    store_b.close()
    assert result["PROCESS_B_PREWRITE_LESSON_FOUND"] is False
    assert result["PROCESS_B_PREWRITE_MEMORY_HIT"] is False
    assert result["PROCESS_B_WRITES_BEFORE_MEMORY_CHECK"] == 0
    assert result["POSTGRES_MEMORY_SURVIVES_NEW_PROCESS"] is False


def test_missing_postgres_url_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_POSTGRES_URL", raising=False)
    evidence = run()
    assert evidence["error"] == "postgres_url_missing"
    assert evidence["P2_1_POSTGRES_QUALIFICATION_PASS"] is False
    assert evidence["create_order_calls"] == 0
    assert os.environ.get("EXCHANGE_WRITE", "").lower() in {"", "false"}


def test_qualification_helper_separates_process_b_from_idempotency() -> None:
    source = (ROOT / "tools/ci/p2_1_postgres_qualification.py").read_text(encoding="utf-8")
    assert "def process_b_prewrite_read(" in source
    assert "def _process_c_idempotency(" in source
    assert source.index("process_b_prewrite_read") < source.index("_process_c_idempotency")
    assert "close_run8_durable_learning(store=store_b" not in source
