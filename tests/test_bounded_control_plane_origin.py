"""Founder Private DEMO RUNTIME REPAIR 1 — bounded-Demo control-plane origin.

Proves the bounded-session control-plane addresses the LIVE learning-validation
long domain (not the dead short alias), via one canonical configurable origin,
and that the launcher's mandatory safety inputs remain intact.
"""
from __future__ import annotations

from pathlib import Path

from tools.ci.p2_migration_service_identity import (
    LEARNING_VALIDATION_ORIGIN,
    LEARNING_VALIDATION_SERVICE_NAME,
    MIGRATION_SERVICE_BASE_NAME,
    learning_validation_origin,
)

LONG = "https://nexus-bybit-demo-learning-validation.zeabur.app"
DEAD_ALIAS = "nexus-bybit-demo-val.zeabur.app"
LAUNCHER = Path(".github/workflows/founder_approved_bybit_demo_bounded_autonomous_session.yml")
STOP = Path(".github/workflows/founder_approved_bybit_demo_bounded_session_stop.yml")
ORCH = Path("tools/ci/demo_bounded_session_orchestrator.py")
PREFLIGHT = Path("tools/ci/demo_bounded_session_preflight.py")


def test_canonical_origin_is_long_domain():
    assert LEARNING_VALIDATION_ORIGIN == LONG
    assert LEARNING_VALIDATION_SERVICE_NAME in LEARNING_VALIDATION_ORIGIN


def test_learning_validation_origin_default_and_override(monkeypatch):
    monkeypatch.delenv("DEMO_VAL_URL", raising=False)
    assert learning_validation_origin() == LONG            # default = long domain
    monkeypatch.setenv("DEMO_VAL_URL", "https://example.test/")
    assert learning_validation_origin() == "https://example.test"  # env override honored
    assert DEAD_ALIAS not in LEARNING_VALIDATION_ORIGIN


def test_bounded_ci_tools_do_not_hardcode_dead_alias():
    for f in (ORCH, PREFLIGHT):
        src = f.read_text(encoding="utf-8")
        assert DEAD_ALIAS not in src, f"{f} still references the dead short alias"
        assert "learning_validation_origin" in src


def test_bounded_workflows_use_long_domain():
    for f in (LAUNCHER, STOP):
        wf = f.read_text(encoding="utf-8")
        assert f"DEMO_VAL_URL: {LONG}" in wf
        assert DEAD_ALIAS not in wf


def test_launcher_mandatory_safety_inputs_preserved():
    wf = LAUNCHER.read_text(encoding="utf-8")
    # Canonical service id retained (migration-control service excluded).
    assert "6a82a79aa21454a2cf6b0015" in wf
    # Founder confirmation phrase mandatory.
    assert "START_NEXUS_BYBIT_DEMO_BOUNDED_6H_SESSION" in wf
    assert 'test "${{ github.event.inputs.confirm }}" = "START_NEXUS_BYBIT_DEMO_BOUNDED_6H_SESSION"' in wf
    # expected_runtime_sha input remains required; dry_run_activate remains supported.
    assert "expected_runtime_sha:" in wf
    assert "dry_run_activate:" in wf
    # required: true appears for the mandatory inputs.
    assert "required: true" in wf


def test_migration_service_is_excluded_from_learning_validation():
    assert LEARNING_VALIDATION_SERVICE_NAME != MIGRATION_SERVICE_BASE_NAME
    assert "p2-migration" not in LEARNING_VALIDATION_ORIGIN
