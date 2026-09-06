"""FOUNDER PRIVATE — PRELIVE POSTGRES PREFLIGHT SECRET-BOUNDARY REPAIR.

Proves the bounded-Demo control plane runs a STRICTLY READ-ONLY Postgres preflight
INSIDE the validation service (over the Zeabur private network) and consumes only
sanitized markers — the GitHub runner never holds the DSN, PostgreSQL Public Port
stays OFF, and the dry preflight can never mutate durable order state. Offline; no
network; no DB; no orders.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

WORKFLOW = Path(".github/workflows/founder_approved_bybit_demo_bounded_autonomous_session.yml")
INRUNTIME = Path("tools/ci/inruntime_postgres_preflight.py")
PREFLIGHT = Path("tools/ci/demo_bounded_session_preflight.py")
CANONICAL_SERVICE_ID = "6a82a79aa21454a2cf6b0015"


def _code_only(src: str) -> str:
    """Strip triple-quoted string/doc blocks and #-comment lines so source scans
    match EXECUTABLE code, not prose that names what the code deliberately avoids."""
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    return "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


irt = _load(INRUNTIME, "inruntime_pg")
pf = _load(PREFLIGHT, "bounded_preflight")

_OK_FACTS = {
    "postgres_available": True, "migration_0007_present": True, "durable_lessons_readable": True,
    "ledger_readable": True, "unresolved_intent_count": 0, "unknown_outcome_count": 0,
}


# --------------------------------------------------------------------------- #
# BLOCKER 1: strictly read-only DB proof (no mutation, no reconcile).
# --------------------------------------------------------------------------- #
def test_inruntime_is_mutation_free_by_construction():
    code = _code_only(INRUNTIME.read_text(encoding="utf-8"))
    for forbidden in ("startup_reconcile", "BybitDemoReconciler", ".transition(",
                      "_postgres_preflight", "INSERT", "UPDATE", "DELETE", "reconcile_intent"):
        assert forbidden not in code, f"in-runtime preflight code must not reference {forbidden!r}"


def test_inruntime_readonly_facts_never_calls_transition_or_reconcile(monkeypatch):
    import backend.nexus_demo_execution.durable_order_ledger as ledgermod
    import backend.nexus_demo_execution.p2_durable_learning_store as lessonmod
    import backend.nexus_persistence_pg.pool as poolmod

    calls = {"transition": 0, "unfinished": 0}

    class _FakePool:
        def __init__(self, url): self.url = url
        def open(self): pass
        def fetchall(self, query, *a, **k):
            return [("0007",)] if "schema_migrations" in query else []
        def close(self): pass

    class _FakeLessonStore:
        def __init__(self, pool=None): pass
        def list_lessons(self): return []
        def close(self): pass

    class _FakeLedger:
        def __init__(self, pool): pass
        def unfinished(self):
            calls["unfinished"] += 1
            return [{"state": "SUBMITTED"}]  # one unresolved intent
        def transition(self, *a, **k):  # must NEVER be called by a read-only preflight
            calls["transition"] += 1

    monkeypatch.setattr(poolmod, "PostgresPool", _FakePool)
    monkeypatch.setattr(ledgermod, "DurableOrderLedger", _FakeLedger)
    monkeypatch.setattr(lessonmod, "DurableLessonStore", _FakeLessonStore)

    markers = irt.to_markers(irt._readonly_facts("fake-dsn"))
    assert calls["transition"] == 0            # DURABLE_LEDGER_TRANSITION_CALLS == 0
    assert calls["unfinished"] == 1            # it only READ the ledger
    assert markers["NO_UNRESOLVED_ORPHAN_INTENTS"] is False  # reported, not mutated
    assert markers["DURABLE_LEDGER_ENTRY_READY"] is False
    assert irt.all_pass(markers) is False       # fail closed


def test_inruntime_markers_pass_and_fail_closed():
    assert irt.all_pass(irt.to_markers(_OK_FACTS)) is True
    assert irt.to_markers(_OK_FACTS)["DURABLE_LEDGER_ENTRY_READY"] is True
    assert irt.all_pass(irt.to_markers({**_OK_FACTS, "unresolved_intent_count": 3})) is False
    assert irt.all_pass(irt.to_markers({**_OK_FACTS, "unknown_outcome_count": 1})) is False
    assert irt.all_pass(irt.to_markers({**_OK_FACTS, "migration_0007_present": False})) is False
    assert irt.all_pass(irt.to_markers({**_OK_FACTS, "ledger_readable": False})) is False
    assert irt.all_pass(irt.to_markers({"postgres_available": False, "error": "X"})) is False


def test_inruntime_missing_runtime_postgres_fails_closed():
    r = subprocess.run(
        [sys.executable, str(INRUNTIME)],
        capture_output=True, text=True,
        env={"PATH": __import__("os").environ.get("PATH", "")},  # no NEXUS_POSTGRES_URL
    )
    assert r.returncode == 1
    assert "VALIDATION_RUNTIME_POSTGRES_MISSING=true" in r.stdout
    assert "INRUNTIME_POSTGRES_PREFLIGHT_PASS=false" in r.stdout


def test_inruntime_never_prints_dsn_or_credentials():
    src = INRUNTIME.read_text(encoding="utf-8")
    for ln in [x for x in src.splitlines() if "print(" in x]:
        low = ln.lower()
        for forbidden in ("nexus_postgres_url", "dsn", "password", "credential", "database_url", "postgresql://"):
            assert forbidden not in low, f"in-runtime print may leak {forbidden!r}: {ln.strip()}"
    markers = irt.to_markers(_OK_FACTS)
    assert set(markers) == set(irt.MARKER_KEYS)
    assert all(isinstance(v, bool) for v in markers.values())


# --------------------------------------------------------------------------- #
# Workflow: private DB path, no runner DSN, auth-login-before-exec, exact id.
# --------------------------------------------------------------------------- #
def _inruntime_step(wf: str) -> str:
    # Extract the in-runtime preflight step block for ordered assertions.
    idx = wf.index("In-runtime Postgres preflight inside validation service")
    nxt = wf.index("- name:", idx + 1)
    return wf[idx:nxt]


def test_workflow_no_runner_postgres_dsn():
    wf = WORKFLOW.read_text(encoding="utf-8")
    assert "NEXUS_STAGING_POSTGRES_URL" not in wf
    assert "NEXUS_POSTGRES_URL: ${{ secrets" not in wf
    assert "GITHUB_RUNNER_POSTGRES_DSN_REQUIRED=no" in wf


def test_workflow_runs_inruntime_preflight_via_service_exec():
    wf = WORKFLOW.read_text(encoding="utf-8")
    assert "zeabur service exec" in wf
    assert "tools.ci.inruntime_postgres_preflight" in wf
    assert "--db-proof-file artifacts/demo_bounded_session/inruntime_db_preflight.txt" in wf
    assert "ZEABUR_TOKEN: ${{ secrets.ZEABUR_TOKEN }}" in wf


def test_workflow_auth_login_before_exec_and_token_not_echoed():
    step = _inruntime_step(WORKFLOW.read_text(encoding="utf-8"))
    assert "zeabur auth login --token" in step
    assert step.index("zeabur auth login --token") < step.index("zeabur service exec"), \
        "auth login must precede service exec"
    # The token is never echoed/printed anywhere in the step.
    for ln in step.splitlines():
        if "echo" in ln:
            assert "ZEABUR_TOKEN" not in ln
    assert "ZEABUR_AUTH_LOGIN_BEFORE_EXEC=yes" in step


def test_workflow_enforces_exact_service_id_before_exec():
    step = _inruntime_step(WORKFLOW.read_text(encoding="utf-8"))
    assert "assert_canonical_validation_service_id" in step
    assert step.index("assert_canonical_validation_service_id") < step.index("zeabur service exec")
    assert "EXACT_VALIDATION_SERVICE_ID_ENFORCED=yes" in step


def test_workflow_exec_is_fail_closed_and_sanitized():
    step = _inruntime_step(WORKFLOW.read_text(encoding="utf-8"))
    assert "INRUNTIME_EXEC_EXIT_CODE" in step
    assert 'test "${EXEC_CODE}" = "0"' in step
    assert "grep -q '^INRUNTIME_POSTGRES_PREFLIGHT_PASS=true$'" in step
    # Only sanitized marker lines are persisted (allow-list grep before writing).
    assert "grep -E \"$ALLOWED\"" in step


# --------------------------------------------------------------------------- #
# BLOCKER 3: exact validation service id enforced (canonical only).
# --------------------------------------------------------------------------- #
def test_exact_validation_service_id_validator():
    from tools.ci.p2_migration_service_identity import (
        MIGRATION_SERVICE_BASE_NAME,
        assert_canonical_validation_service_id,
    )
    import pytest as _pytest

    assert assert_canonical_validation_service_id(CANONICAL_SERVICE_ID) == CANONICAL_SERVICE_ID
    for bad in ("", None, "  ", MIGRATION_SERVICE_BASE_NAME, "deadbeefdeadbeefdeadbeef", CANONICAL_SERVICE_ID + "x"):
        with _pytest.raises(ValueError):
            assert_canonical_validation_service_id(bad)


# --------------------------------------------------------------------------- #
# Runner preflight consumes sanitized DB proof; never opens Postgres.
# --------------------------------------------------------------------------- #
def _proof(**over):
    base = {k: True for k in (
        "POSTGRES_AVAILABLE", "MIGRATION_0007_PRESENT", "DURABLE_LESSONS_READABLE",
        "DURABLE_ORDER_LEDGER_READABLE", "NO_UNRESOLVED_ORPHAN_INTENTS",
        "NO_UNKNOWN_OUTCOME_STATE", "DURABLE_LEDGER_ENTRY_READY", "INRUNTIME_POSTGRES_PREFLIGHT_PASS",
    )}
    base.update(over)
    return base


def test_apply_db_checks_consumes_passing_proof():
    checks, problems = {}, []
    pf._apply_db_checks(checks, problems, offline=False, db_proof=_proof())
    assert problems == []
    assert checks["POSTGRES_AVAILABLE"] and checks["DB_PROOF_FROM_VALIDATION_RUNTIME"]
    assert checks["DURABLE_LEDGER_ENTRY_READY"] and checks["DURABLE_ORDER_LEDGER_READABLE"]


def test_apply_db_checks_missing_proof_fails_closed():
    checks, problems = {}, []
    pf._apply_db_checks(checks, problems, offline=False, db_proof=None)
    assert "inruntime_db_proof_missing" in problems and checks["POSTGRES_AVAILABLE"] is False


def test_apply_db_checks_unresolved_intent_fails_closed():
    checks, problems = {}, []
    pf._apply_db_checks(checks, problems, offline=False,
                        db_proof=_proof(NO_UNRESOLVED_ORPHAN_INTENTS=False, DURABLE_LEDGER_ENTRY_READY=False))
    assert "unresolved_or_orphan_intent" in problems


def test_apply_db_checks_migration_missing_fails_closed():
    checks, problems = {}, []
    pf._apply_db_checks(checks, problems, offline=False,
                        db_proof=_proof(MIGRATION_0007_PRESENT=False, DURABLE_LEDGER_ENTRY_READY=False))
    assert "migration_0007_missing" in problems


def test_apply_db_checks_runtime_postgres_missing_marker_fails_closed():
    checks, problems = {}, []
    pf._apply_db_checks(checks, problems, offline=False,
                        db_proof={"VALIDATION_RUNTIME_POSTGRES_MISSING": True, "INRUNTIME_POSTGRES_PREFLIGHT_PASS": False})
    assert "validation_runtime_postgres_missing" in problems


def test_parse_db_proof_reads_markers():
    proof = pf.parse_db_proof(
        "POSTGRES_AVAILABLE=true\nDURABLE_LEDGER_ENTRY_READY=true\nNO_UNKNOWN_OUTCOME_STATE=false\n"
        "INRUNTIME_POSTGRES_PREFLIGHT_PASS=true\nnoise\n"
    )
    assert proof["POSTGRES_AVAILABLE"] is True and proof["NO_UNKNOWN_OUTCOME_STATE"] is False
    assert proof["INRUNTIME_POSTGRES_PREFLIGHT_PASS"] is True


def test_runner_preflight_has_no_direct_postgres_path():
    src = PREFLIGHT.read_text(encoding="utf-8")
    code = _code_only(src)
    assert 'os.environ.get("NEXUS_STAGING_POSTGRES_URL")' not in code
    assert "_postgres_preflight" not in code          # dead mutating path removed
    assert "BybitDemoReconciler" not in code and "startup_reconcile" not in code
    assert "db_proof" in src and "_apply_db_checks" in src


def test_offline_preflight_preserves_demo_safety_invariants(monkeypatch):
    for k in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        monkeypatch.setenv(k, "false")
    monkeypatch.setenv("NEXUS_DATA_ROOT", str(Path("artifacts/test_prelive_boundary_data").resolve()))
    report = pf.run_preflight(offline=True, founder_phrase="START_NEXUS_BYBIT_DEMO_BOUNDED_6H_SESSION")
    c = report["checks"]
    assert c["MAINNET_FALSE"] and c["REAL_MONEY_FALSE"] and c["EXCHANGE_WRITE_FALSE"]
    assert c["DB_PROOF_FROM_VALIDATION_RUNTIME"] and c["DURABLE_LEDGER_ENTRY_READY"]
