"""PUB2-F Pass 3 independent cross-review probes."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_public_auth.entitlements import assign_tier_manual, require_feature
from backend.nexus_public_auth.hard_bans import HardBanViolation, run_hard_ban_pass
from backend.nexus_public_auth.mfa import MfaService
from backend.nexus_public_auth.pass_runner import run_three_passes
from backend.nexus_public_auth.rate_limit import AuthRateLimiter, RateLimitExceeded
from backend.nexus_public_auth.service import PublicAuthMembershipService
from backend.nexus_public_auth.store import PublicAuthStore


ROOT = Path(__file__).resolve().parents[2]


def test_pass3_independent_cross_review_runner():
    result = run_hard_ban_pass(3, ROOT)
    assert result["pass_id"] == 3
    assert result["ok"] is True
    assert result["adversarial"]["executed"] is True
    assert result["adversarial"]["ok"] is True
    assert result["adversarial"]["pass_kind"] == "independent_cross_review"
    names = {p["name"] for p in result["adversarial"]["probes"]}
    assert "rate_limit_burst" in names
    assert "mfa_wrong_code" in names
    assert "iap_actor_blocked" in names
    assert "enterprise_cannot_private_execution_access" in names
    assert "p3_private_execution" in names
    assert "mfa_challenge_session_replay" in names
    assert "org_privilege_escalation" in names
    assert "tier_matrix_mutation" in names
    assert "rate_limit_empty_subject" in names


def test_pass3_not_summary_only():
    """Pass 3 must exercise live break attempts, not only restate Pass 2."""
    result = run_three_passes(ROOT)
    p2_names = {p["name"] for p in result["pass2"]["adversarial"]["probes"]}
    p3_names = {p["name"] for p in result["pass3"]["adversarial"]["probes"]}
    unique = p3_names - p2_names
    assert "rate_limit_burst" in unique
    assert "mfa_wrong_code" in unique
    assert "iap_actor_blocked" in unique
    assert "mfa_challenge_session_replay" in unique
    assert "org_privilege_escalation" in unique


def test_iap_actor_cannot_assign_enterprise():
    with pytest.raises(HardBanViolation):
        assign_tier_manual(
            current_tier="Free", target_tier="Enterprise", actor="iap:google_tx"
        )


def test_require_feature_blocks_execution_scopes():
    with pytest.raises(HardBanViolation):
        require_feature("Enterprise", "autonomy_control")
    with pytest.raises(HardBanViolation):
        require_feature("Pro", "order_placement")


def test_rate_limiter_and_mfa_failure_modes():
    limiter = AuthRateLimiter(window_seconds=60, limits={"export": 1})
    limiter.check("export", "acct_z")
    with pytest.raises(RateLimitExceeded):
        limiter.check("export", "acct_z")

    store = PublicAuthStore()
    svc = PublicAuthMembershipService(
        store=store,
        rate_limiter=AuthRateLimiter(limits={"register": 20, "mfa_challenge": 50}),
    )
    reg = svc.register_member("p3@example.com", "P3")
    mfa = MfaService(store)
    enrolled = mfa.enroll_factor(reg["account_id"], "recovery_codes")
    mfa.confirm_enrollment(
        reg["account_id"],
        enrolled["factor_id"],
        enrollment_secret=enrolled["enrollment_secret_once"],
    )
    challenge = mfa.create_challenge(reg["account_id"], enrolled["factor_id"])
    with pytest.raises(HardBanViolation):
        mfa.verify_challenge(
            reg["account_id"],
            challenge["challenge_id"],
            response_code="deadbeefdeadbeefdeadbeefdeadbeef",
        )


def test_mfa_challenge_cannot_mint_two_sessions():
    store = PublicAuthStore()
    svc = PublicAuthMembershipService(
        store=store,
        rate_limiter=AuthRateLimiter(limits={"register": 20, "session_create": 50}),
    )
    reg = svc.register_member("replay@example.com", "Replay")
    enrolled = svc.mfa.enroll_factor(reg["account_id"], "totp")
    svc.mfa.confirm_enrollment(
        reg["account_id"],
        enrolled["factor_id"],
        enrollment_secret=enrolled["enrollment_secret_once"],
    )
    challenge = svc.mfa.create_challenge(reg["account_id"], enrolled["factor_id"])
    svc.mfa.verify_challenge(
        reg["account_id"],
        challenge["challenge_id"],
        response_code=challenge["stub_response_hint"],
    )
    svc.sessions.create_session(
        reg["account_id"],
        tier="Free",
        member_roles=["member"],
        mfa_challenge_id=challenge["challenge_id"],
    )
    with pytest.raises(HardBanViolation):
        svc.sessions.create_session(
            reg["account_id"],
            tier="Free",
            member_roles=["member"],
            mfa_challenge_id=challenge["challenge_id"],
        )


def test_org_billing_viewer_cannot_escalate():
    store = PublicAuthStore()
    svc = PublicAuthMembershipService(
        store=store, rate_limiter=AuthRateLimiter(limits={"register": 20})
    )
    owner = svc.register_member("o@example.com", "O")
    viewer = svc.register_member("v@example.com", "V")
    org = svc.create_org(owner_account_id=owner["account_id"], name="Org1")
    svc.add_org_member(
        actor_account_id=owner["account_id"],
        org_id=org["org_id"],
        member_account_id=viewer["account_id"],
        roles=["org_billing_viewer"],
    )
    with pytest.raises(HardBanViolation):
        svc.assign_org_roles(
            viewer["account_id"],
            org["org_id"],
            ["org_admin"],
            actor_account_id=viewer["account_id"],
        )
