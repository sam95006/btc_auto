from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_private_cert.certifier import run_certification
from backend.nexus_private_cert.safety import safety_gate

REPO = Path(__file__).resolve().parents[2]
NEW_WF = REPO / ".github" / "workflows" / "founder_approved_private_env2_certification.yml"
CERT_SRC = REPO / "backend" / "nexus_private_cert"

SAFE_ENV = {
    "BYBIT_DEMO": "true",
    "MAINNET": "false",
    "REAL_MONEY": "false",
    "EXCHANGE_WRITE": "false",
    "DEMO_AUTONOMOUS_ENABLED": "false",
    "AUTONOMOUS_SEND": "false",
}

AI_KEY_ENVS = ("GROQ_API_KEY_PRIMARY", "GROQ_API_KEY_SECONDARY", "CEREBRAS_API_KEY", "SAMBANOVA_API_KEY")


class FakeReaderFail:
    api_key = "x"
    api_secret = "y"

    def read_snapshot(self):
        raise RuntimeError("auth_failed")


class FakePool:
    def __init__(self, *, ready=True, applied=("0007", "0014"), tables=None, unresolved=0):
        self._ready = ready
        self._applied = list(applied)
        self._tables = list(tables if tables is not None else [
            "bybit_demo_order_intents", "bybit_demo_order_state_history",
            "lesson_candidates", "reflections", "decision_memory", "runtime_evidence_events",
        ])
        self._unresolved = unresolved

    def readiness(self):
        return {"ready": self._ready, "reason": None if self._ready else "down"}

    def fetchall(self, sql, params=()):
        if "schema_migrations" in sql:
            return [(v,) for v in self._applied]
        if "information_schema.tables" in sql:
            return [(t,) for t in self._tables]
        return []

    def fetchval(self, sql, params=()):
        return self._unresolved


def _no_ai_keys(monkeypatch):
    for k in AI_KEY_ENVS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NEXUS_AI_MOCK", "0")


# --------------------------------------------------------------------------
# A / B — new certification workflow does not couple GitHub to Postgres/secrets
# --------------------------------------------------------------------------

def test_A_new_workflow_no_postgres_url() -> None:
    src = NEW_WF.read_text(encoding="utf-8")
    assert "NEXUS_STAGING_POSTGRES_URL" not in src
    assert "NEXUS_POSTGRES_URL" not in src


def test_B_new_workflow_no_direct_pg_and_no_credentialed_secrets() -> None:
    src = NEW_WF.read_text(encoding="utf-8")
    for banned in ("psql ", "psycopg", "postgresql://", "p1_mask_dsn"):
        assert banned not in src
    # The workflow must not carry DB/Bybit/AI secrets — only a control secret.
    for banned in ("BYBIT_DEMO_API_SECRET", "GROQ_API_KEY", "CEREBRAS_API_KEY", "SAMBANOVA_API_KEY", "DATABASE_URL"):
        assert banned not in src
    assert "NEXUS_BOUNDED_SESSION_CONTROL_SECRET" in src  # control-secret auth only


# --------------------------------------------------------------------------
# C — safety hard-fail (fail-closed before any external call)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("flag,val", [
    ("MAINNET", "true"), ("REAL_MONEY", "true"), ("EXCHANGE_WRITE", "true"),
    ("DEMO_AUTONOMOUS_ENABLED", "true"), ("AUTONOMOUS_SEND", "true"), ("BYBIT_DEMO", "false"),
])
def test_C_safety_block(flag, val) -> None:
    env = dict(SAFE_ENV)
    env[flag] = val
    r = run_certification(pool=FakePool(), env=env, bybit_reader=FakeReaderFail())
    assert r["private_env2_pass"] is False
    assert r["blocked_reason"] == "SAFETY_BLOCK"
    assert r["ai"]["GROQ_MAIN_REASONER"] == "NOT_RUN"  # no external call happened
    assert r["orders_submitted"] == 0 and r["cancels"] == 0 and r["position_mutations"] == 0


# --------------------------------------------------------------------------
# D — no order/cancel/position-mutating path in the certifier
# --------------------------------------------------------------------------

def test_D_no_mutating_calls_in_source() -> None:
    blob = ""
    for p in CERT_SRC.glob("*.py"):
        blob += p.read_text(encoding="utf-8").lower()
    for banned in ("/v5/order/create", "order/cancel", "order/amend", "place_order", "submit_order",
                   "set-leverage", "position/trading-stop", "demo_write_client", "close_position"):
        assert banned not in blob, banned
    # The bybit module only allows read paths.
    bysrc = (CERT_SRC / "bybit_readonly.py").read_text(encoding="utf-8")
    assert "market/time" in bysrc and "instruments-info" in bysrc and "user/query-api" in bysrc


# --------------------------------------------------------------------------
# E / F / G — no secret ever returned in the certification payload
# --------------------------------------------------------------------------

def test_EFG_no_secret_material_in_output(monkeypatch) -> None:
    _no_ai_keys(monkeypatch)
    monkeypatch.setenv("NEXUS_POSTGRES_URL", "")
    r = run_certification(pool=FakePool(), env=SAFE_ENV, bybit_reader=FakeReaderFail())
    blob = repr(r).lower()
    for banned in ("api_key", "api_secret", "authorization", "x-bapi-sign", "password",
                   "postgresql://", "dsn", "bearer "):
        assert banned not in blob, banned


# --------------------------------------------------------------------------
# H — AI NOT_CONFIGURED fails certification
# --------------------------------------------------------------------------

def test_H_ai_not_configured_fails(monkeypatch) -> None:
    _no_ai_keys(monkeypatch)
    r = run_certification(pool=FakePool(), env=SAFE_ENV, bybit_reader=FakeReaderFail())
    assert r["ai"]["GROQ_MAIN_REASONER"] == "NOT_CONFIGURED"
    assert r["private_env2_pass"] is False
    assert "AI_NOT_ALL_REAL_API_PASS" in r["blocked_reason"]


# --------------------------------------------------------------------------
# I — Bybit auth failure fails certification
# --------------------------------------------------------------------------

def test_I_bybit_auth_failure_fails(monkeypatch) -> None:
    _no_ai_keys(monkeypatch)
    r = run_certification(pool=FakePool(), env=SAFE_ENV, bybit_reader=FakeReaderFail())
    assert r["bybit_demo"]["auth"] == "FAIL"
    assert r["bybit_demo"]["orders_submitted"] == 0
    assert r["private_env2_pass"] is False
    assert "BYBIT_READONLY_INCOMPLETE" in r["blocked_reason"]


# --------------------------------------------------------------------------
# J — PostgreSQL unavailable fails certification
# --------------------------------------------------------------------------

def test_J_postgres_unavailable_fails(monkeypatch) -> None:
    _no_ai_keys(monkeypatch)
    r = run_certification(pool=None, env=SAFE_ENV, bybit_reader=FakeReaderFail())
    assert r["postgres"]["postgres_available"] is False
    assert r["private_env2_pass"] is False
    assert "POSTGRES_DURABILITY_INCOMPLETE" in r["blocked_reason"]


# --------------------------------------------------------------------------
# K — unresolved ledger state fails certification
# --------------------------------------------------------------------------

def test_K_unresolved_ledger_fails(monkeypatch) -> None:
    _no_ai_keys(monkeypatch)
    pool = FakePool(unresolved=3)
    r = run_certification(pool=pool, env=SAFE_ENV, bybit_reader=FakeReaderFail())
    assert r["postgres"]["postgres_available"] is True
    assert r["postgres"]["no_unresolved_intent"] is False
    assert r["private_env2_pass"] is False
    assert "POSTGRES_DURABILITY_INCOMPLETE" in r["blocked_reason"]


# --------------------------------------------------------------------------
# safety_gate unit
# --------------------------------------------------------------------------

def test_safety_gate_ok() -> None:
    ok, detail = safety_gate(SAFE_ENV)
    assert ok is True and detail["violations"] == []


# --------------------------------------------------------------------------
# PRIVATE-ENV-2F hardening
# --------------------------------------------------------------------------

def test_unset_critical_safety_flag_fails_closed() -> None:
    # An unset REAL_MONEY must NOT silently count as an explicit false.
    env = dict(SAFE_ENV)
    del env["REAL_MONEY"]
    ok, detail = safety_gate(env)
    assert ok is False and any("REAL_MONEY" in v for v in detail["violations"])
    r = run_certification(pool=FakePool(), env=env, bybit_reader=FakeReaderFail())
    assert r["private_env2_pass"] is False and r["blocked_reason"] == "SAFETY_BLOCK"


def test_uid_skipped_does_not_certify(monkeypatch) -> None:
    _no_ai_keys(monkeypatch)
    monkeypatch.setenv("NEXUS_POSTGRES_URL", "")
    # Everything green except UID = SKIPPED.
    monkeypatch.setattr(
        "backend.nexus_private_cert.bybit_readonly.bybit_readonly_preflight",
        lambda **kw: {"auth": "PASS", "uid_binding": "SKIPPED", "balance_read": "PASS",
                      "positions_read": "PASS", "instrument_read": "PASS", "clock_skew_ok": "PASS",
                      "account_flat": True, "orders_submitted": 0, "cancels": 0, "position_mutations": 0},
    )
    monkeypatch.setattr("backend.nexus_private_cert.certifier._run_ai_smoke",
                        lambda gw: {"statuses": {p: "REAL_API_PASS" for p in
                                    ("GROQ_MAIN_REASONER", "GROQ_REFLECTION_REASONER",
                                     "CEREBRAS_RESEARCH_NORMALIZER", "SAMBANOVA_INDEPENDENT_CRITIC")},
                                    "models": {}, "all_pass": True})
    r = run_certification(pool=FakePool(), env=SAFE_ENV)
    assert r["bybit_demo"]["uid_binding"] == "SKIPPED"
    assert r["private_env2_pass"] is False
    assert "BYBIT_READONLY_INCOMPLETE" in r["blocked_reason"]


def test_certifier_uses_canonical_postgres_url_binding() -> None:
    # The certifier pool binding reads NEXUS_POSTGRES_URL directly and does not
    # gate on the product-alpha NEXUS_PG_RUNTIME_ENABLED flag.
    src = (REPO / "backend" / "nexus_private_cert" / "routes.py").read_text(encoding="utf-8")
    assert "NEXUS_POSTGRES_URL" in src
    assert "cfg.enabled" not in src and "PostgresRuntimeConfig" not in src


def test_full_pass_path(monkeypatch) -> None:
    _no_ai_keys(monkeypatch)
    monkeypatch.setenv("NEXUS_POSTGRES_URL", "")
    monkeypatch.setattr(
        "backend.nexus_private_cert.bybit_readonly.bybit_readonly_preflight",
        lambda **kw: {"auth": "PASS", "uid_binding": "PASS", "balance_read": "PASS",
                      "positions_read": "PASS", "instrument_read": "PASS", "clock_skew_ok": "PASS",
                      "account_flat": True, "orders_submitted": 0, "cancels": 0, "position_mutations": 0},
    )
    monkeypatch.setattr("backend.nexus_private_cert.certifier._run_ai_smoke",
                        lambda gw: {"statuses": {p: "REAL_API_PASS" for p in
                                    ("GROQ_MAIN_REASONER", "GROQ_REFLECTION_REASONER",
                                     "CEREBRAS_RESEARCH_NORMALIZER", "SAMBANOVA_INDEPENDENT_CRITIC")},
                                    "models": {}, "all_pass": True})
    r = run_certification(pool=FakePool(unresolved=0), env=SAFE_ENV)
    assert r["private_env2_pass"] is True and "blocked_reason" not in r
    assert r["orders_submitted"] == 0 and r["cancels"] == 0 and r["position_mutations"] == 0
