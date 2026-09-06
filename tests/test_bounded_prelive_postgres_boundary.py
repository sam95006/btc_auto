"""FOUNDER PRIVATE — PRELIVE POSTGRES PREFLIGHT SECRET-BOUNDARY REPAIR.

Proves the bounded-Demo control plane runs its Postgres preflight INSIDE the
validation service (over the Zeabur private network) and consumes only sanitized
markers — the GitHub runner never holds the DSN and the PostgreSQL Public Port
stays OFF. Offline; no network; no DB; no orders.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

WORKFLOW = Path(".github/workflows/founder_approved_bybit_demo_bounded_autonomous_session.yml")
INRUNTIME = Path("tools/ci/inruntime_postgres_preflight.py")
PREFLIGHT = Path("tools/ci/demo_bounded_session_preflight.py")
SERVICE_ID = "6a82a79aa21454a2cf6b0015"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


irt = _load(INRUNTIME, "inruntime_pg")
pf = _load(PREFLIGHT, "bounded_preflight")

_OK = {
    "postgres_available": True, "migration_0007_present": True, "durable_lessons_readable": True,
    "unresolved_intent_count": 0, "orphan_positions": 0, "unknown_outcome_count": 0, "entries_allowed": True,
}


# --------------------------------------------------------------------------- #
# Workflow: no runner Postgres DSN; DB preflight runs inside the service.
# --------------------------------------------------------------------------- #
def test_workflow_does_not_require_runner_postgres_dsn():
    wf = WORKFLOW.read_text(encoding="utf-8")
    # The runner must not be handed the staging Postgres DSN anywhere.
    assert "secrets.NEXUS_STAGING_POSTGRES_URL" not in wf
    assert "NEXUS_STAGING_POSTGRES_URL" not in wf
    # And the live preflight step no longer injects a Postgres URL to the runner.
    assert "NEXUS_POSTGRES_URL: ${{ secrets" not in wf


def test_workflow_runs_inruntime_preflight_via_zeabur_service_exec():
    wf = WORKFLOW.read_text(encoding="utf-8")
    assert "zeabur service exec" in wf
    assert "tools.ci.inruntime_postgres_preflight" in wf
    assert "INRUNTIME_POSTGRES_PREFLIGHT_PASS=true" in wf
    # Uses the canonical validation service id + env, and the Zeabur control token.
    assert SERVICE_ID in wf
    assert "ZEABUR_TOKEN: ${{ secrets.ZEABUR_TOKEN }}" in wf
    assert "ZEABUR_ENV_ID" in wf
    # Live preflight consumes the sanitized in-runtime DB proof file.
    assert "--db-proof-file artifacts/demo_bounded_session/inruntime_db_preflight.txt" in wf


# --------------------------------------------------------------------------- #
# In-runtime script: sanitized, DSN never printed, fail-closed.
# --------------------------------------------------------------------------- #
def test_inruntime_markers_all_pass_and_fail_closed():
    assert irt.all_pass(irt.to_markers(_OK)) is True
    assert irt.all_pass(irt.to_markers({**_OK, "unresolved_intent_count": 3})) is False   # unresolved intents
    assert irt.all_pass(irt.to_markers({**_OK, "orphan_positions": 1})) is False           # orphan position
    assert irt.all_pass(irt.to_markers({**_OK, "unknown_outcome_count": 1})) is False      # unknown outcome
    assert irt.all_pass(irt.to_markers({**_OK, "migration_0007_present": False})) is False # migration 0007 missing
    assert irt.all_pass(irt.to_markers({**_OK, "entries_allowed": False})) is False        # reconcile blocks entry
    assert irt.all_pass(irt.to_markers({"postgres_available": False, "error": "x"})) is False


def test_inruntime_missing_runtime_postgres_fails_closed(monkeypatch):
    # No NEXUS_POSTGRES_URL in the (service) environment -> explicit missing marker
    # + fail closed, WITHOUT importing DB modules or injecting any DSN.
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
    print_lines = [ln for ln in src.splitlines() if "print(" in ln]
    for ln in print_lines:
        low = ln.lower()
        for forbidden in ("nexus_postgres_url", "dsn", "password", "credential", "database_url", "postgresql://"):
            assert forbidden not in low, f"in-runtime preflight print may leak {forbidden!r}: {ln.strip()}"
    # to_markers returns only boolean markers (no raw counts / DSN).
    markers = irt.to_markers(_OK)
    assert set(markers) == set(irt.MARKER_KEYS)
    assert all(isinstance(v, bool) for v in markers.values())


# --------------------------------------------------------------------------- #
# Runner preflight: consumes sanitized DB proof; never opens Postgres.
# --------------------------------------------------------------------------- #
def _proof(**over):
    base = {k: True for k in (
        "POSTGRES_AVAILABLE", "MIGRATION_0007_PRESENT", "DURABLE_LESSONS_READABLE",
        "NO_UNRESOLVED_ORPHAN_INTENTS", "NO_UNKNOWN_OUTCOME_STATE",
        "STARTUP_RECONCILIATION_ENTRIES_ALLOWED", "INRUNTIME_POSTGRES_PREFLIGHT_PASS",
    )}
    base.update(over)
    return base


def test_apply_db_checks_consumes_passing_proof():
    checks, problems = {}, []
    pf._apply_db_checks(checks, problems, offline=False, db_proof=_proof())
    assert problems == []
    assert checks["POSTGRES_AVAILABLE"] and checks["DB_PROOF_FROM_VALIDATION_RUNTIME"]
    assert checks["STARTUP_RECONCILIATION_ENTRIES_ALLOWED"]


def test_apply_db_checks_missing_proof_fails_closed():
    checks, problems = {}, []
    pf._apply_db_checks(checks, problems, offline=False, db_proof=None)
    assert "inruntime_db_proof_missing" in problems
    assert checks["POSTGRES_AVAILABLE"] is False


def test_apply_db_checks_unresolved_intent_fails_closed():
    checks, problems = {}, []
    pf._apply_db_checks(checks, problems, offline=False, db_proof=_proof(NO_UNRESOLVED_ORPHAN_INTENTS=False))
    assert "unresolved_or_orphan_intent" in problems


def test_apply_db_checks_migration_missing_fails_closed():
    checks, problems = {}, []
    pf._apply_db_checks(checks, problems, offline=False, db_proof=_proof(MIGRATION_0007_PRESENT=False))
    assert "migration_0007_missing" in problems


def test_apply_db_checks_runtime_postgres_missing_marker_fails_closed():
    checks, problems = {}, []
    pf._apply_db_checks(checks, problems, offline=False,
                        db_proof={"VALIDATION_RUNTIME_POSTGRES_MISSING": True, "INRUNTIME_POSTGRES_PREFLIGHT_PASS": False})
    assert "validation_runtime_postgres_missing" in problems


def test_parse_db_proof_reads_markers():
    text = ("POSTGRES_AVAILABLE=true\nMIGRATION_0007_PRESENT=true\nNO_UNKNOWN_OUTCOME_STATE=false\n"
            "INRUNTIME_POSTGRES_PREFLIGHT_PASS=true\nnoise line\n")
    proof = pf.parse_db_proof(text)
    assert proof["POSTGRES_AVAILABLE"] is True
    assert proof["NO_UNKNOWN_OUTCOME_STATE"] is False
    assert proof["INRUNTIME_POSTGRES_PREFLIGHT_PASS"] is True


def test_offline_preflight_preserves_demo_safety_invariants(monkeypatch):
    for k in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        monkeypatch.setenv(k, "false")
    monkeypatch.setenv("NEXUS_DATA_ROOT", str(Path("artifacts/test_prelive_boundary_data").resolve()))
    report = pf.run_preflight(offline=True, founder_phrase="START_NEXUS_BYBIT_DEMO_BOUNDED_6H_SESSION")
    c = report["checks"]
    assert c["MAINNET_FALSE"] and c["REAL_MONEY_FALSE"] and c["EXCHANGE_WRITE_FALSE"]
    assert c["DB_PROOF_FROM_VALIDATION_RUNTIME"] and c["STARTUP_RECONCILIATION_ENTRIES_ALLOWED"]


def test_runner_preflight_no_longer_reads_staging_dsn_env():
    # The runner code path must not fall back to a runner-held Postgres DSN.
    src = PREFLIGHT.read_text(encoding="utf-8")
    assert 'os.environ.get("NEXUS_STAGING_POSTGRES_URL")' not in src
    # run_preflight's DB path is driven by db_proof, not a direct connection.
    assert "db_proof" in src and "_apply_db_checks" in src
