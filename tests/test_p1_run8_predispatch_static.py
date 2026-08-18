"""Static pre-dispatch tests for Run #8 parser, SHA identity, and bootstrap split."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

import sys

from backend.nexus_demo_execution.p1_run8_accounting_recovery import run_recovery_with_probes
from backend.nexus_demo_execution.p1_validation_runtime import code_identity_matches

sys.path.insert(0, str(Path("tools/ci").resolve()))
from p1_parse_run8_recovery_json import main as parse_run8_main  # noqa: E402
from p1_zeabur_transport import (  # noqa: E402
    parse_recovery_evidence,
    parse_run8_accounting_recovery_evidence,
    parse_run8_bootstrap_failure_evidence,
)


def _run8_payload(*, verdict: str = "HOLD") -> dict:
    payload = {
        "BYBIT_DEMO_SINGLE_TRADE_E2E_PASS": verdict,
        "AUTONOMOUS_BYBIT_DEMO_ARM_READY": "HOLD",
        "recovery_stage": "LEDGER_FINALIZATION" if verdict == "PASS" else "CLOSED_PNL_READ",
        "candidate_count": 1,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
        "P1_ENTRY_RECONCILIATION_PASS": verdict == "PASS",
        "P1_CLOSE_RECONCILIATION_PASS": verdict == "PASS",
        "P1_EXCHANGE_REALIZED_PNL_PASS": verdict == "PASS",
        "P1_DURABLE_LEDGER_LIFECYCLE_PASS": verdict == "PASS",
        "P1_RUN8_POSITION_FLAT": verdict == "PASS",
        "P1_RUN8_EXACT_CLOSED_PNL_MATCH": verdict == "PASS",
        "P1_RUN8_LEDGER_FINALIZED": verdict == "PASS",
        "entry_read_pass": True,
        "close_read_pass": True,
        "position_flat": True,
        "execution_identity_pass": True,
        "closed_pnl_exact_match": verdict == "PASS",
        "ledger_finalization_pass": verdict == "PASS",
        "error": None if verdict == "PASS" else "exact_closed_pnl_unavailable",
    }
    return payload


def _run2_payload() -> dict:
    return {
        "P1_RUN2_RECOVERY_CLEAR": "PASS",
        "run2_order_count_found": 0,
        "run2_position_count_found": 0,
        "p1_unresolved_ledger_count": 0,
        "migration_0005_present": True,
        "migration_0006_present": True,
        "recent_order_history_count": 0,
        "recent_execution_count": 0,
        "recent_closed_pnl_count": 0,
        "p1_identity_exchange_row_count": 0,
        "p1_state_counts": {},
        "p1_transition_history_count": 0,
        "error": None,
    }


def test_valid_run8_pass_json_parser_exit_0(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_run8_payload(verdict="PASS"))))
    assert parse_run8_main([]) == 0
    parsed = parse_run8_accounting_recovery_evidence(json.dumps(_run8_payload(verdict="PASS")))
    assert parsed["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "PASS"


def test_valid_run8_hold_json_parser_exit_1(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_run8_payload())))
    assert parse_run8_main([]) == 1


def test_run2_json_rejected_by_run8_parser():
    with pytest.raises(ValueError, match="run2_schema"):
        parse_run8_accounting_recovery_evidence(json.dumps(_run2_payload()))
    assert parse_recovery_evidence(json.dumps(_run2_payload()))["P1_RUN2_RECOVERY_CLEAR"] == "PASS"


def test_run8_json_without_run2_keys_accepted():
    payload = _run8_payload(verdict="HOLD")
    assert "P1_RUN2_RECOVERY_CLEAR" not in payload
    parsed = parse_run8_accounting_recovery_evidence(json.dumps(payload))
    assert parsed["candidate_count"] == 1


def test_missing_deployment_sha_holds(monkeypatch):
    monkeypatch.delenv("NEXUS_EXPECTED_SHA", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.delenv("NEXUS_DEPLOYMENT_SHA", raising=False)
    monkeypatch.delenv("NEXUS_DEPLOYMENT_ID", raising=False)
    evidence = run_recovery_with_probes()
    assert evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "HOLD"
    assert evidence["recovery_stage"] == "CODE_IDENTITY"
    assert evidence["create_order_calls"] == 0
    assert evidence["exchange_write_call_count"] == 0
    assert code_identity_matches(expected_sha="", loaded_sha="abc", require_both=True) is False


def test_stale_deployment_sha_holds(monkeypatch):
    monkeypatch.setenv("NEXUS_EXPECTED_SHA", "aaaaaaaaaaaaaaaa")
    monkeypatch.setenv("GITHUB_SHA", "aaaaaaaaaaaaaaaa")
    monkeypatch.setenv("NEXUS_DEPLOYMENT_SHA", "bbbbbbbbbbbbbbbb")
    monkeypatch.setenv("NEXUS_DEPLOYMENT_ID", "bbbbbbbbbbbbbbbb")
    evidence = run_recovery_with_probes()
    assert evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "HOLD"
    assert evidence["recovery_stage"] == "CODE_IDENTITY"
    assert evidence["error"] == "code_identity_mismatch"
    assert evidence["create_order_calls"] == 0
    assert evidence["exchange_write_call_count"] == 0


def test_exact_deployment_sha_passes_identity_gate(monkeypatch):
    sha = "87329d24c741d2172b795c6eb5f5b96a0f7af3bf"
    monkeypatch.setenv("NEXUS_EXPECTED_SHA", sha)
    monkeypatch.setenv("GITHUB_SHA", sha)
    monkeypatch.setenv("NEXUS_DEPLOYMENT_SHA", sha)
    monkeypatch.setenv("NEXUS_DEPLOYMENT_ID", sha)
    monkeypatch.delenv("NEXUS_POSTGRES_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    evidence = run_recovery_with_probes()
    assert evidence["code_identity_pass"] is True
    assert evidence["recovery_stage"] != "CODE_IDENTITY"
    assert evidence["error"] == "ledger_dsn_missing"
    assert evidence["create_order_calls"] == 0
    assert evidence["exchange_write_call_count"] == 0


def test_bootstrap_import_failure_writes_only_bootstrap_evidence(tmp_path, monkeypatch):
    evidence_path = tmp_path / "p1_run8_accounting_recovery_evidence.json"
    bootstrap_path = tmp_path / "p1_run8_bootstrap_failure.json"
    monkeypatch.setenv("P1_EVIDENCE_PATH", str(evidence_path))
    monkeypatch.setenv("P1_BOOTSTRAP_FAILURE_PATH", str(bootstrap_path))
    import backend.nexus_demo_execution.p1_run8_accounting_recovery_bootstrap as bootstrap

    def explode():
        raise RuntimeError("postgres://user:secret@host/db")

    monkeypatch.setattr(
        "backend.nexus_demo_execution.p1_run8_accounting_recovery.run_recovery_with_probes",
        explode,
    )
    rc = bootstrap.main()
    assert rc == 1
    assert not evidence_path.exists()
    fail = json.loads(bootstrap_path.read_text(encoding="utf-8"))
    parse_run8_bootstrap_failure_evidence(json.dumps(fail))
    assert fail["recovery_stage"] == "MODULE_IMPORT"
    assert fail["exception_type"] == "RuntimeError"
    assert "postgres://" not in json.dumps(fail)
    assert fail["create_order_calls"] == 0
    assert fail["exchange_write_call_count"] == 0
    assert fail["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "HOLD"


def test_pool_close_failure_stage_is_pool_close(monkeypatch):
    class FakePool:
        def open(self):
            return None

        def fetchval(self, *_a, **_k):
            return 1

        def fetchval(self, *_a, **_k):
            return 1

        def close(self):
            raise RuntimeError("pool boom")

    class FakeLedger:
        def required_migrations_present(self):
            return {"migration_0005_present": True, "migration_0006_present": True}

    monkeypatch.setenv("NEXUS_EXPECTED_SHA", "deadbeefcafebabe")
    monkeypatch.setenv("NEXUS_DEPLOYMENT_SHA", "deadbeefcafebabe")
    monkeypatch.setenv("NEXUS_DEPLOYMENT_ID", "deadbeefcafebabe")
    monkeypatch.setenv("NEXUS_POSTGRES_URL", "postgresql://unused")
    monkeypatch.setattr(
        "backend.nexus_persistence_pg.pool.PostgresPool",
        lambda *_a, **_k: FakePool(),
    )
    monkeypatch.setattr(
        "backend.nexus_demo_execution.durable_order_ledger.DurableOrderLedger",
        lambda *_a, **_k: FakeLedger(),
    )
    monkeypatch.setattr(
        "backend.nexus_demo_execution.demo_write_client.DemoWriteClient",
        lambda *_a, **_k: object(),
    )
    monkeypatch.setattr(
        "backend.nexus_demo_execution.p1_run8_accounting_recovery.recover_run8_accounting",
        lambda **_k: {
            "BYBIT_DEMO_SINGLE_TRADE_E2E_PASS": "HOLD",
            "create_order_calls": 0,
            "exchange_write_call_count": 0,
        },
    )
    evidence = run_recovery_with_probes()
    assert evidence["recovery_stage"] == "POOL_CLOSE"
    assert evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "HOLD"
    assert evidence["create_order_calls"] == 0
    assert evidence["exchange_write_call_count"] == 0


def test_every_failure_has_zero_exchange_writes(monkeypatch):
    monkeypatch.delenv("NEXUS_EXPECTED_SHA", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.delenv("NEXUS_DEPLOYMENT_SHA", raising=False)
    evidence = run_recovery_with_probes()
    assert evidence["create_order_calls"] == 0
    assert evidence["exchange_write_call_count"] == 0


def test_workflow_sets_deployment_sha_identity():
    source = Path(".github/workflows/founder_approved_bybit_demo_p1_run8_accounting_recovery.yml").read_text(
        encoding="utf-8"
    )
    assert 'set_var NEXUS_DEPLOYMENT_SHA "$GITHUB_SHA"' in source
    assert 'set_var NEXUS_DEPLOYMENT_ID "$GITHUB_SHA"' in source
    assert 'set_var GITHUB_SHA "$GITHUB_SHA"' in source
    assert "NEXUS_DEPLOYMENT_SHA=${GITHUB_SHA}" in source
    assert "p1_parse_run8_recovery_json.py --bootstrap" in source
    assert "parse_recovery_evidence" not in source
