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
