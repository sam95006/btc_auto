"""Guards for the STAGING-ONLY operator password-recovery script.

Security-critical, DB-independent behavior: the script must refuse to run outside
staging, require both inputs, reject weak passwords, and never echo the email or
password. (The DB mutation path is exercised only against a real staging DB via
the Founder-approved workflow.)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path("tools/ci/staging_member_password_recovery.py")
SECRET_PW = "sup3r-secret-recovery-pw"
SECRET_EMAIL = "founder-recovery@example.com"


def _run(env: dict[str, str]):
    base = {"PATH": __import__("os").environ.get("PATH", "")}
    base.update(env)
    return subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, env=base)


def test_refuses_outside_staging():
    r = _run({"NEXUS_ENV": "production",
              "NEXUS_STAGING_RECOVERY_EMAIL": SECRET_EMAIL,
              "NEXUS_STAGING_RECOVERY_PASSWORD": SECRET_PW})
    assert r.returncode == 1
    assert "RECOVERY_REFUSED_NON_STAGING=yes" in r.stdout
    assert "RECOVERY_OK=yes" not in r.stdout


def test_requires_both_inputs():
    r = _run({"NEXUS_ENV": "staging"})
    assert r.returncode == 1
    assert "RECOVERY_MISSING_INPUTS=yes" in r.stdout


def test_rejects_weak_password():
    r = _run({"NEXUS_ENV": "staging",
              "NEXUS_STAGING_RECOVERY_EMAIL": SECRET_EMAIL,
              "NEXUS_STAGING_RECOVERY_PASSWORD": "short"})
    assert r.returncode == 1
    assert "RECOVERY_WEAK_PASSWORD=yes" in r.stdout


def test_recovery_uses_canonical_password_policy_not_a_weaker_one():
    # The recovery path must enforce the SAME canonical minimum as the customer
    # reset path (MemberEmailService), which is 12 — NOT the earlier local 8.
    from backend.nexus_product_backend.email_auth import MIN_PASSWORD_LENGTH
    assert MIN_PASSWORD_LENGTH >= 12
    # A password the canonical auth path would reject (>=8 but <MIN) must also be
    # rejected by recovery — proving no independent weaker policy remains.
    too_short = "a" * (MIN_PASSWORD_LENGTH - 1)
    assert len(too_short) >= 8
    r = _run({"NEXUS_ENV": "staging",
              "NEXUS_STAGING_RECOVERY_EMAIL": SECRET_EMAIL,
              "NEXUS_STAGING_RECOVERY_PASSWORD": too_short})
    assert r.returncode == 1
    assert "RECOVERY_WEAK_PASSWORD=yes" in r.stdout
    # And the script imports the single canonical constant rather than hard-coding.
    src = SCRIPT.read_text(encoding="utf-8")
    assert "from backend.nexus_product_backend.email_auth import MIN_PASSWORD_LENGTH" in src
    assert "< 8" not in src


def test_never_prints_email_or_password():
    r = _run({"NEXUS_ENV": "staging",
              "NEXUS_STAGING_RECOVERY_EMAIL": SECRET_EMAIL,
              "NEXUS_STAGING_RECOVERY_PASSWORD": SECRET_PW})
    combined = r.stdout + r.stderr
    assert SECRET_PW not in combined
    assert SECRET_EMAIL not in combined


def test_script_uses_canonical_hasher_and_preserves_immutable_fields():
    src = SCRIPT.read_text(encoding="utf-8")
    # Canonical Argon2 hasher via the auth service; fail closed if unavailable.
    assert "AuthAlphaService" in src and "_hasher" in src
    assert "RECOVERY_HASHER_UNAVAILABLE=yes" in src
    assert "update_password_hash" in src and "revoke_all_sessions" in src
    assert "append_product_audit" in src
    assert "RECOVERY_ACCOUNT_NOT_RESOLVED=yes" in src   # fail closed if not unique
    # Never mutate identity / plan / trial.
    for forbidden in ("created_at", "registered_at", "plan", "trial", "subscription", "delete"):
        assert f"update_{forbidden}" not in src


def test_immutable_proof_is_a_real_before_after_check():
    src = SCRIPT.read_text(encoding="utf-8")
    # A real runtime snapshot compares account_id + created_at before/after and
    # fails closed on any change or re-resolve failure.
    assert "_immutable_snapshot" in src
    assert "created_at" in src
    assert "RECOVERY_IMMUTABLE_FIELDS_CHANGED=yes" in src
    assert "RECOVERY_ACCOUNT_RERESOLVE_FAILED=yes" in src
    # The success marker is only printed AFTER the after-snapshot comparison.
    before_idx = src.index("before = _immutable_snapshot")
    after_idx = src.index("after = _immutable_snapshot")
    ok_idx = src.index("ACCOUNT_IMMUTABLE_FIELDS_UNCHANGED=yes")
    assert before_idx < after_idx < ok_idx


def test_recovery_workflow_is_ref_and_environment_protected():
    wf = Path(".github/workflows/founder_approved_staging_member_recovery.yml").read_text(encoding="utf-8")
    assert "permissions:\n  contents: read" in wf
    assert "environment: staging-member-recovery" in wf
    # Fail-closed main-ref guard before any secret-consuming step.
    assert 'github.ref }}" != "refs/heads/main"' in wf
    assert "RECOVERY_REF_REFUSED=yes" in wf
    # Secrets are consumed only as env (never as workflow inputs).
    assert "NEXUS_STAGING_RECOVERY_PASSWORD: ${{ secrets.NEXUS_STAGING_RECOVERY_PASSWORD }}" in wf
    assert "inputs.password" not in wf.lower().replace(" ", "")
