"""Guards for the narrow authenticated Personal staging E2E.

Network-independent and DB-independent: the pure trial/catalog validators, the
secret-safety of the runner, and the ref+Environment protection of the workflow.
The LIVE authenticated path is exercised only against real staging via the
Founder-approved workflow. Crucially, the validator is cross-checked against the
REAL backend trial functions so the E2E contract can never silently drift.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT = Path("tools/ci/personal_authenticated_staging_e2e.py")
WORKFLOW = Path(".github/workflows/personal_authenticated_staging_e2e.yml")


def _load_e2e():
    spec = importlib.util.spec_from_file_location("personal_e2e_mod", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


e2e = _load_e2e()


# --------------------------------------------------------------------------- #
# Pure trial-truth validator.
# --------------------------------------------------------------------------- #
def _contract():
    from backend.nexus_platform.plans import public_catalog

    return public_catalog()["trial"]


def test_paid_state_passes():
    e2e.validate_trial_truth(
        "pro",
        {"state": "PAID", "plan": "pro", "trial_active": False},
        _contract(),
    )


def test_active_trial_passes():
    e2e.validate_trial_truth(
        "starter",
        {"state": "TRIAL", "trial_active": True, "days_remaining": 12,
         "trial_ends_at": "2026-10-01T00:00:00+00:00"},
        _contract(),
    )


def test_expired_trial_must_be_free():
    e2e.validate_trial_truth(
        "free",
        {"state": "TRIAL_EXPIRED", "trial_active": False, "days_remaining": 0},
        _contract(),
    )
    with pytest.raises(e2e.E2EError):
        e2e.validate_trial_truth(
            "starter",  # expired but still Starter -> inconsistent
            {"state": "TRIAL_EXPIRED", "trial_active": False, "days_remaining": 0},
            _contract(),
        )


def test_unavailable_state_fails_closed():
    with pytest.raises(e2e.E2EError):
        e2e.validate_trial_truth("free", {"state": "UNAVAILABLE", "trial_active": False}, _contract())


def test_contract_drift_fails_closed():
    for bad in ({"days": 14}, {"on_expiry": "auto_upgrade"}, {"auto_charge": True}):
        contract = {**_contract(), **bad}
        with pytest.raises(e2e.E2EError):
            e2e.validate_trial_truth(
                "starter",
                {"state": "TRIAL", "trial_active": True, "days_remaining": 5,
                 "trial_ends_at": "2026-10-01T00:00:00+00:00"},
                contract,
            )


def test_validator_accepts_real_backend_trial_outputs():
    """Cross-check: genuine outputs of the backend trial functions must satisfy
    the validator for every real state (active / expired / paid). This binds the
    E2E contract to the product's own trial semantics."""
    from backend.nexus_platform import plans as _plans
    from backend.nexus_platform import trial as _trial

    contract = _plans.public_catalog()["trial"]
    now = datetime(2026, 9, 4, tzinfo=timezone.utc)

    # Active trial (registered 5 days ago, no paid plan).
    reg_recent = now - timedelta(days=5)
    e2e.validate_trial_truth(
        _trial.effective_plan(now, registered_at=reg_recent, paid_plan=None),
        _trial.trial_status(now, registered_at=reg_recent, paid_plan=None),
        contract,
    )
    # Expired trial (registered 60 days ago, no paid plan) => Free.
    reg_old = now - timedelta(days=60)
    e2e.validate_trial_truth(
        _trial.effective_plan(now, registered_at=reg_old, paid_plan=None),
        _trial.trial_status(now, registered_at=reg_old, paid_plan=None),
        contract,
    )
    # Paid wins regardless of trial window.
    e2e.validate_trial_truth(
        _trial.effective_plan(now, registered_at=reg_old, paid_plan="advanced"),
        _trial.trial_status(now, registered_at=reg_old, paid_plan="advanced"),
        contract,
    )


# --------------------------------------------------------------------------- #
# Catalog validator.
# --------------------------------------------------------------------------- #
def test_membership_catalog_from_backend_is_valid():
    from backend.nexus_platform.plans import public_catalog

    e2e.validate_membership_catalog({"commercial": public_catalog()})


def test_catalog_requires_enterprise_separate():
    catalog = {"commercial": {"plans": [
        {"code": "free"}, {"code": "starter"}, {"code": "pro"}, {"code": "advanced"},
        {"code": "enterprise", "contact_sales": False, "monthly_usd": 99.0},
    ]}}
    with pytest.raises(e2e.E2EError):
        e2e.validate_membership_catalog(catalog)


def test_catalog_requires_all_personal_plans():
    catalog = {"commercial": {"plans": [
        {"code": "free"}, {"code": "starter"}, {"code": "pro"},
        {"code": "enterprise", "contact_sales": True, "monthly_usd": None},
    ]}}
    with pytest.raises(e2e.E2EError):
        e2e.validate_membership_catalog(catalog)


# --------------------------------------------------------------------------- #
# Secrecy: the sanitized view never leaks the registration origin.
# --------------------------------------------------------------------------- #
def test_sanitized_view_excludes_registration_origin():
    view = e2e.sanitized_subscription_view(
        "starter",
        {"state": "TRIAL", "trial_active": True, "days_remaining": 9,
         "trial_started_at": "2026-08-01T00:00:00+00:00",   # == created_at: must NOT leak
         "trial_ends_at": "2026-08-31T00:00:00+00:00"},
        _contract(),
    )
    assert "trial_started_at" not in view
    assert "created_at" not in view
    assert view["trial_ends_at"] == "2026-08-31T00:00:00+00:00"  # explicitly allowed field
    assert set(view) == {
        "effective_plan", "trial_active", "trial_state",
        "days_remaining", "trial_ends_at", "auto_charge",
    }


# --------------------------------------------------------------------------- #
# Runner secret-safety (no network needed for the missing-input path).
# --------------------------------------------------------------------------- #
def test_runner_fails_closed_without_inputs():
    r = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True,
        env={"PATH": __import__("os").environ.get("PATH", "")},
    )
    assert r.returncode == 1
    assert "E2E_MISSING_INPUTS=yes" in r.stdout
    assert "AUTHENTICATED_WORKSTREAM_B_E2E=no" in r.stdout


def test_runner_source_never_prints_credentials_or_identity():
    src = SCRIPT.read_text(encoding="utf-8")
    # In-memory cookie jar; never a manual cookie injection or persisted jar.
    assert "http.cookiejar.CookieJar()" in src
    assert "MozillaCookieJar" not in src and ".save(" not in src
    # No print() statement may echo credential / identity / registration-origin
    # material (docstring mentions of these words are fine — only prints matter).
    print_lines = [ln for ln in src.splitlines() if "print(" in ln]
    for ln in print_lines:
        low = ln.lower()
        for forbidden in ("password", "csrf", "cookie", "account_id",
                          "trial_started_at", "created_at", "authorization"):
            assert forbidden not in low, f"print may leak {forbidden!r}: {ln.strip()}"
        # 'email' as a bare word must not be printed (guard against f-strings).
        assert "email" not in low or "e2e_missing_inputs" in low
    # Authenticates via the REAL product login endpoint (no injected/forged
    # session): the only session material is what that endpoint returns.
    assert "/api/v1/member/session/login" in src
    assert 'json_body={"email": email, "password": password}' in src


# --------------------------------------------------------------------------- #
# Workflow protection.
# --------------------------------------------------------------------------- #
def test_workflow_is_ref_and_environment_protected():
    wf = WORKFLOW.read_text(encoding="utf-8")
    assert "permissions:\n  contents: read" in wf
    assert "environment: staging-personal-e2e" in wf
    assert 'github.ref }}" != "refs/heads/main"' in wf
    assert "E2E_REF_REFUSED=yes" in wf
    assert "E2E_REF_OK=yes" in wf
    # Secrets consumed only as env, never as workflow inputs.
    assert "NEXUS_STAGING_E2E_PASSWORD: ${{ secrets.NEXUS_STAGING_E2E_PASSWORD }}" in wf
    assert "inputs.password" not in wf.lower().replace(" ", "")
    # Never any direct DB access from this workflow (scan executable YAML only;
    # the header comment may say it does NOT touch Postgres).
    exec_yaml = "\n".join(ln for ln in wf.splitlines() if not ln.lstrip().startswith("#")).lower()
    for db in ("postgres", "psql", "nexus_staging_postgres_url", "database_url"):
        assert db not in exec_yaml
