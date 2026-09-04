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
SMOKE = Path("tools/ci/personal_browser_smoke.py")
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


def test_enterprise_is_never_a_personal_effective_plan():
    # Enterprise is a separate product; a Personal subscription reporting
    # effective_plan=enterprise must fail closed (in ANY state).
    assert "enterprise" not in e2e.PAID_PLANS
    with pytest.raises(e2e.E2EError):
        e2e.validate_trial_truth(
            "enterprise",
            {"state": "PAID", "plan": "enterprise", "trial_active": False},
            _contract(),
        )


# --------------------------------------------------------------------------- #
# LIVE trial registration-anchor proof.
# --------------------------------------------------------------------------- #
def test_registration_anchor_matching_origin_passes():
    e2e.validate_registration_anchor(
        "2026-08-01T00:00:00+00:00",
        {"trial_started_at": "2026-08-01T00:00:00+00:00",
         "trial_ends_at": "2026-08-31T00:00:00+00:00"},  # exactly 30 days
    )


def test_registration_anchor_accepts_equivalent_instant_across_tz_forms():
    # Same instant expressed with 'Z' vs +00:00 must still match.
    e2e.validate_registration_anchor(
        "2026-08-01T00:00:00Z",
        {"trial_started_at": "2026-08-01T00:00:00+00:00",
         "trial_ends_at": "2026-08-31T00:00:00+00:00"},
    )


def test_registration_anchor_mismatched_origin_fails():
    with pytest.raises(e2e.E2EError):
        e2e.validate_registration_anchor(
            "2026-08-01T00:00:00+00:00",
            {"trial_started_at": "2026-08-02T00:00:00+00:00",   # != registration
             "trial_ends_at": "2026-09-01T00:00:00+00:00"},
        )


def test_registration_anchor_non_30_day_interval_fails():
    with pytest.raises(e2e.E2EError):
        e2e.validate_registration_anchor(
            "2026-08-01T00:00:00+00:00",
            {"trial_started_at": "2026-08-01T00:00:00+00:00",
             "trial_ends_at": "2026-08-30T00:00:00+00:00"},   # 29 days
        )


def test_registration_anchor_missing_or_malformed_fails_closed():
    # Missing session created_at.
    with pytest.raises(e2e.E2EError):
        e2e.validate_registration_anchor(
            None, {"trial_started_at": "2026-08-01T00:00:00+00:00",
                   "trial_ends_at": "2026-08-31T00:00:00+00:00"})
    # Missing trial timestamps.
    with pytest.raises(e2e.E2EError):
        e2e.validate_registration_anchor("2026-08-01T00:00:00+00:00", {})
    # Malformed timestamp.
    with pytest.raises(e2e.E2EError):
        e2e.validate_registration_anchor(
            "not-a-timestamp",
            {"trial_started_at": "2026-08-01T00:00:00+00:00",
             "trial_ends_at": "2026-08-31T00:00:00+00:00"})


def test_registration_anchor_matches_real_backend_trial_output():
    """Genuine backend trial output for a freshly-registered account must satisfy
    the anchor: trial_started_at == registered_at and a 30-day window."""
    from datetime import datetime, timedelta, timezone

    from backend.nexus_platform import trial as _trial

    now = datetime(2026, 9, 4, tzinfo=timezone.utc)
    reg = now - timedelta(days=5)
    status = _trial.trial_status(now, registered_at=reg, paid_plan=None)
    e2e.validate_registration_anchor(reg.isoformat(), status)


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
# Browser smoke: secret-safe, correctness-only, two viewports (source scan so it
# runs without Playwright installed).
# --------------------------------------------------------------------------- #
def test_browser_smoke_is_secret_safe_and_correctness_only():
    src = SMOKE.read_text(encoding="utf-8")
    # Exactly the two required viewports.
    assert "1440" in src and "900" in src
    assert "390" in src and "844" in src
    # Real UI login via typed fields; credentials are filled, never printed.
    assert ".fill(email)" in src and ".fill(password)" in src
    print_lines = [ln for ln in src.splitlines() if "print(" in ln]
    for ln in print_lines:
        low = ln.lower()
        for forbidden in ("password", "email", "cookie", "session id",
                          "created_at", "storage_state"):
            assert forbidden not in low, f"smoke print may leak {forbidden!r}: {ln.strip()}"
    # Fresh incognito context per viewport; no on-disk session persistence.
    assert "new_context(" in src
    assert "storage_state" not in src and ".save(" not in src
    # Correctness assertions present: session-persist, plans, enterprise-separate,
    # no-founder/trading UI, logout+redirect.
    for needed in ("session_did_not_persist", "plan-advanced", "enterprise",
                   "FORBIDDEN_UI_TERMS", "登出", "post_logout_app_not_redirected_to_login"):
        assert needed in src
    # Emits the two runtime markers.
    assert "PERSONAL_DESKTOP_RUNTIME" in src and "PERSONAL_MOBILE_RUNTIME" in src


def test_browser_smoke_forbids_founder_and_trading_ui_terms():
    src = SMOKE.read_text(encoding="utf-8")
    for term in ("下單", "槓桿", "leverage", "position size", "founder", "bybit"):
        assert term in src, f"smoke must screen for {term!r}"


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
    for db in ("psql", "nexus_staging_postgres_url", "database_url"):
        assert db not in exec_yaml
    # "postgres" may appear only inside the Playwright system-deps install
    # (playwright install --with-deps pulls OS libs), never as a DB step.
    for ln in exec_yaml.splitlines():
        if "postgres" in ln:
            assert "playwright" in ln, f"unexpected postgres reference: {ln.strip()}"
    # The browser smoke runs both viewports via the dedicated script, using the
    # same Environment secrets only as env.
    assert "tools/ci/personal_browser_smoke.py" in wf
    assert "python -m playwright install" in wf
    assert "NEXUS_STAGING_E2E_PASSWORD: ${{ secrets.NEXUS_STAGING_E2E_PASSWORD }}" in wf
