"""Unit coverage for PUB2-H org ACL and decision opaque deny."""
from __future__ import annotations

import pytest

from backend.nexus_public_auth.hard_bans import HardBanViolation
from backend.nexus_public_auth.org_access import assert_no_private_execution_features
from backend.nexus_public_auth.service import PublicAuthMembershipService
from backend.nexus_public_auth.store import PublicAuthStore
from backend.nexus_public_decision_cloud import service as decision_service
from backend.nexus_public_decision_cloud.store import load_catalog


def test_private_execution_features_denied():
    with pytest.raises(HardBanViolation):
        assert_no_private_execution_features({"decision_feed_read", "exchange_write"})


def test_org_owner_can_add_member():
    store = PublicAuthStore()
    svc = PublicAuthMembershipService(store=store)
    owner = svc.register_member("o@ex.com", "O")
    member = svc.register_member("m@ex.com", "M")
    org = svc.create_org(owner_account_id=owner["account_id"], name="Org")
    result = svc.add_org_member(
        actor_account_id=owner["account_id"],
        org_id=org["org_id"],
        member_account_id=member["account_id"],
        roles=["org_billing_viewer"],
    )
    assert result["roles"] == ["org_billing_viewer"]
    acct = store.get_account(member["account_id"])
    assert "org_billing_viewer" in acct.org_roles[org["org_id"]]


def test_decision_opaque_deny_and_allow():
    load_catalog(reload=True)
    deny = decision_service.decision_detail("dec_org_scoped_hidden")
    allow = decision_service.decision_detail(
        "dec_org_scoped_hidden", caller_org_ids={"org_redteam_alpha"}
    )
    assert deny["ok"] is False
    assert allow["ok"] is True
    assert allow["decision"]["decision_id"] == "dec_org_scoped_hidden"
