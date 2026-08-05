"""PUB2-F Pass 1 hard-ban verification."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_public_auth.hard_bans import (
    HardBanViolation,
    assert_env_hard_bans,
    assert_tier_matrix_excludes_private_execution,
    env_hard_ban_guard,
    refuse_live_billing,
    refuse_private_execution_via_entitlement,
    run_hard_ban_pass,
    scan_owned_paths_for_banned_claims,
    validate_public_issuer,
    validate_public_realm,
)
from backend.nexus_public_auth.constants import PUBLIC_IDENTITY_REALM, PUBLIC_JWT_ISSUER


ROOT = Path(__file__).resolve().parents[2]


def test_env_hard_ban_guard_ok_by_default(monkeypatch):
    for key in (
        "NEXUS_PUBLIC_LIVE_BILLING",
        "NEXUS_PUBLIC_REAL_IAP",
        "NEXUS_PUBLIC_PRODUCTION_CUSTOMER_DB",
        "NEXUS_PUBLIC_LIVE_DEPLOY",
        "NEXUS_PUBLIC_SHARE_PRIVATE_JWT",
        "NEXUS_PUBLIC_REUSE_PRIVATE_ADMIN_SESSION",
        "NEXUS_PUBLIC_PRIVATE_EXECUTION_VIA_ENTITLEMENT",
        "EXCHANGE_WRITE",
        "MAINNET",
        "REAL_MONEY",
    ):
        monkeypatch.delenv(key, raising=False)
    result = env_hard_ban_guard()
    assert result["ok"] is True
    assert_env_hard_bans()
    assert_tier_matrix_excludes_private_execution()


def test_env_hard_ban_guard_blocks_live_billing(monkeypatch):
    monkeypatch.setenv("NEXUS_PUBLIC_LIVE_BILLING", "true")
    result = env_hard_ban_guard()
    assert result["ok"] is False
    assert "LIVE_BILLING" in result["violations"]
    with pytest.raises(HardBanViolation):
        assert_env_hard_bans()


def test_env_blocks_private_execution_via_entitlement_flag(monkeypatch):
    monkeypatch.setenv("NEXUS_PUBLIC_PRIVATE_EXECUTION_VIA_ENTITLEMENT", "true")
    result = env_hard_ban_guard()
    assert result["ok"] is False
    assert "PRIVATE_EXECUTION_VIA_ENTITLEMENT" in result["violations"]


def test_public_issuer_and_realm_validation():
    validate_public_issuer(PUBLIC_JWT_ISSUER)
    validate_public_realm(PUBLIC_IDENTITY_REALM)
    with pytest.raises(HardBanViolation):
        validate_public_issuer("nexus-private-auth")
    with pytest.raises(HardBanViolation):
        validate_public_realm("nexus.private.identity.v1")


def test_refuse_live_billing_and_private_execution():
    with pytest.raises(HardBanViolation):
        refuse_live_billing()
    with pytest.raises(HardBanViolation):
        refuse_private_execution_via_entitlement()


def test_pass1_scan_and_runner():
    scan = scan_owned_paths_for_banned_claims(ROOT)
    assert scan["ok"] is True, scan["hits"]
    result = run_hard_ban_pass(1, ROOT)
    assert result["pass_id"] == 1
    assert result["ok"] is True
    assert result["env"]["ok"] is True
    assert result["private_execution_access_via_entitlement"] is False
