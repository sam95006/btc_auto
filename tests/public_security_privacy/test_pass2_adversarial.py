"""PUB2-H Pass 2 — adversarial re-probes after remediation."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_public_auth.hard_bans import HardBanViolation
from backend.nexus_public_auth.service import PublicAuthMembershipService
from backend.nexus_public_auth.store import PublicAuthStore
from backend.nexus_public_decision_cloud import service as decision_service
from backend.nexus_public_decision_cloud.store import load_catalog
from backend.nexus_public_security_privacy_redteam import run_pass
from backend.nexus_public_security_privacy_redteam.hard_bans import refuse_exchange_write

ROOT = Path(__file__).resolve().parents[2]


def test_pass2_adversarial_runner():
    result = run_pass(2, ROOT)
    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["status_scan"]["ok"] is True


def test_pass2_cannot_enumerate_org_decision():
    load_catalog(reload=True)
    missing = decision_service.decision_detail("nope")
    hidden = decision_service.decision_detail("dec_org_scoped_hidden")
    assert missing["error"] == hidden["error"] == "decision_unavailable"
    assert set(missing.keys()) == set(hidden.keys())


def test_pass2_cross_org_export_denied():
    store = PublicAuthStore()
    svc = PublicAuthMembershipService(store=store)
    a = svc.register_member("a@ex.com", "A")
    b = svc.register_member("b@ex.com", "B")
    with pytest.raises(HardBanViolation):
        svc.lifecycle.export_account_data(a["account_id"], actor_account_id=b["account_id"])


def test_pass2_exchange_write_refused():
    with pytest.raises(Exception):
        refuse_exchange_write()
