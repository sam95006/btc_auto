"""PUB2-H Pass 3 — independent break attempts."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_publishing_gateway.deny_traps import find_denied_fields
from backend.nexus_publishing_gateway.exceptions import PublishingGatewayError
from backend.nexus_publishing_gateway.gateway import publish_intelligence
from backend.nexus_publishing_gateway.side_channel import SAFE_PUBLIC_SEED
from backend.nexus_public_auth.hard_bans import HardBanViolation
from backend.nexus_public_auth.service import PublicAuthMembershipService
from backend.nexus_public_auth.store import PublicAuthStore
from backend.nexus_public_security_privacy_redteam import run_three_passes

ROOT = Path(__file__).resolve().parents[2]


def test_pass3_three_passes_clean():
    result = run_three_passes(ROOT)
    assert result["ok"] is True
    assert result["status"] == "PASS"
    assert result["survivors"] == []
    assert result["blockers"] == []
    assert result["pass_count"] == 3
    assert all(p["ok"] for p in result["passes"])


def test_pass3_break_self_register_enterprise():
    svc = PublicAuthMembershipService(store=PublicAuthStore())
    with pytest.raises(HardBanViolation):
        svc.register_member("break@ex.com", "Break", tier="Enterprise")


def test_pass3_break_prompt_publish():
    dirty = {
        **SAFE_PUBLIC_SEED,
        "system_prompt": "leak me",
        "lesson_memory": {"x": 1},
    }
    assert find_denied_fields(dirty)
    with pytest.raises(PublishingGatewayError):
        publish_intelligence(dirty, environment="LOCAL")


def test_pass3_break_foreign_org_owner_grant():
    store = PublicAuthStore()
    svc = PublicAuthMembershipService(store=store)
    a = svc.register_member("a@ex.com", "A")
    b = svc.register_member("b@ex.com", "B")
    org = svc.create_org(owner_account_id=a["account_id"], name="A-Org")
    svc.add_org_member(
        actor_account_id=a["account_id"],
        org_id=org["org_id"],
        member_account_id=b["account_id"],
        roles=["org_member"],
    )
    with pytest.raises(HardBanViolation):
        svc.assign_org_roles(
            b["account_id"],
            org["org_id"],
            ["org_owner"],
            actor_account_id=b["account_id"],
        )
