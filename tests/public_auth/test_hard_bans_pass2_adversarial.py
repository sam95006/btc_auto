"""PUB2-F Pass 2 adversarial hard-ban probes."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_public_auth.entitlements import has_feature
from backend.nexus_public_auth.hard_bans import HardBanViolation, run_hard_ban_pass
from backend.nexus_public_auth.jwt_issuer import PublicJwtIssuer, PUBLIC_JWT_SECRET_ENV
from backend.nexus_public_auth.pass_runner import run_three_passes, run_two_passes
from backend.nexus_public_auth.roles import normalize_member_roles
from backend.nexus_public_auth.service import PublicAuthMembershipService
from backend.nexus_public_auth.store import PublicAuthStore, enable_live_billing_forbidden


ROOT = Path(__file__).resolve().parents[2]


def test_pass2_adversarial_runner():
    result = run_hard_ban_pass(2, ROOT)
    assert result["pass_id"] == 2
    assert result["ok"] is True
    assert result["adversarial"]["executed"] is True
    assert result["adversarial"]["ok"] is True
    names = {p["name"] for p in result["adversarial"]["probes"]}
    assert "live_billing" in names
    assert "shared_private_jwt" in names
    assert "private_admin_session" in names
    assert "private_execution_via_entitlement" in names
    assert any(n.startswith("entitlement_Enterprise_") for n in names)


def test_three_passes_ok():
    result = run_three_passes(ROOT)
    assert result["lane"] == "PUB2-F"
    assert result["ok"] is True
    assert result["pass1"]["ok"] is True
    assert result["pass2"]["ok"] is True
    assert result["pass3"]["ok"] is True
    assert result["shared_JWT_issuer_count"] == 0
    assert result["live_billing_enabled"] is False
    assert result["private_admin_session_reuse_count"] == 0
    assert result["private_execution_access_via_entitlement"] is False
    assert result["mfa_ready"] is True
    assert result["rate_limits_enabled"] is True


def test_two_passes_alias_still_runs_three():
    result = run_two_passes(ROOT)
    assert result["ok"] is True
    assert "pass3" in result


def test_cannot_construct_issuer_from_private_secret_env():
    with pytest.raises(HardBanViolation):
        PublicJwtIssuer(secret="x" * 32, secret_env="NEXUS_PRIVATE_JWT_SECRET")


def test_cannot_override_issuer_claims():
    issuer = PublicJwtIssuer(secret="public-test-secret-value")
    with pytest.raises(HardBanViolation):
        issuer.issue(
            account_id="acct_x",
            tier="Free",
            member_roles=["member"],
            extra_claims={"iss": "nexus-private-auth"},
        )


def test_private_founder_role_rejected():
    with pytest.raises(HardBanViolation):
        normalize_member_roles(["founder_admin"])


def test_private_admin_token_rejected_by_session_service():
    store = PublicAuthStore()
    svc = PublicAuthMembershipService(store=store)
    foreign = PublicJwtIssuer(secret="other-public-secret-xxxx")
    issued = foreign.issue(account_id="acct_y", tier="Free", member_roles=["member"])
    with pytest.raises(HardBanViolation):
        svc.sessions.reject_private_admin_token(
            issued["token"], claimed_issuer="nexus-private"
        )


def test_enable_live_billing_forbidden():
    with pytest.raises(HardBanViolation):
        enable_live_billing_forbidden()


def test_public_secret_env_name_constant():
    assert PUBLIC_JWT_SECRET_ENV == "NEXUS_PUBLIC_JWT_SECRET"


def test_enterprise_cannot_gain_private_execution():
    with pytest.raises(HardBanViolation):
        has_feature("Enterprise", "private_execution_access")
    with pytest.raises(HardBanViolation):
        has_feature("Elite", "exchange_write")
