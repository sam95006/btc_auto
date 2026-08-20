"""Offline P2.1 postgres qualification helper tests. No exchange writes."""
from __future__ import annotations

import json
import os
from pathlib import Path

from tests.test_p2_durable_learning_closure import _durable_run8_intents
from tools.ci.p2_1_postgres_qualification import run


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


def test_sqlite_restart_and_duplicate_and_unrelated_context(tmp_path: Path) -> None:
    evidence = run(intents=_durable_run8_intents(), sqlite_path=tmp_path / "p2_qual.db")
    assert evidence["POSTGRES_LESSON_PERSISTED"] is True
    assert evidence["POSTGRES_MEMORY_SURVIVES_NEW_PROCESS"] is True
    assert evidence["DUPLICATE_LESSON_COUNT"] == 1
    assert evidence["DUPLICATE_LESSON_IDEMPOTENCY_PASS"] is True
    assert evidence["POLICY_TRUTH"] is False
    assert evidence["SUPPORT_COUNT"] == 1
    assert evidence["research_recommendation_after"] == "RESEARCH_SKIP"
    assert evidence["unrelated_research_recommendation"] == "RESEARCH_ALLOW"
    assert evidence["create_order_calls"] == 0
    assert evidence["exchange_write_call_count"] == 0
    assert evidence["AUTONOMOUS_BYBIT_DEMO_ARM_READY"] == "HOLD"
    assert evidence["P2_1_POSTGRES_QUALIFICATION_PASS"] is True
    assert "run8_certified" not in json.dumps(evidence)


def test_missing_postgres_url_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_POSTGRES_URL", raising=False)
    evidence = run()
    assert evidence["error"] == "postgres_url_missing"
    assert evidence["P2_1_POSTGRES_QUALIFICATION_PASS"] is False
    assert evidence["create_order_calls"] == 0
    assert os.environ.get("EXCHANGE_WRITE", "").lower() in {"", "false"}
