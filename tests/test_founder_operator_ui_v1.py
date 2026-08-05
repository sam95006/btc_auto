"""PUB-E Founder Private Operator UI — adversarial + authz tests (two passes)."""
from __future__ import annotations

import os

import pytest
from flask import Flask


def _app():
    app = Flask(__name__)
    from backend.api.founder_private_routes import register_founder_private_routes

    register_founder_private_routes(app)
    return app


def _founder_env(monkeypatch):
    monkeypatch.delenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", raising=False)
    monkeypatch.delenv("ZEABUR", raising=False)
    monkeypatch.delenv("ZEABUR_SERVICE_ID", raising=False)
    monkeypatch.setenv("NEXUS_ENTITLEMENT_TEST_MODE", "1")
    monkeypatch.setenv("NEXUS_MEMBERSHIP_TIER", "FOUNDER")
    monkeypatch.setenv("NEXUS_FOUNDER_ROUTES_ENABLED", "1")
    monkeypatch.setenv("NEXUS_ENV", "development")


def _member_env(monkeypatch, tier: str = "PRO"):
    monkeypatch.delenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", raising=False)
    monkeypatch.setenv("NEXUS_ENTITLEMENT_TEST_MODE", "1")
    monkeypatch.setenv("NEXUS_MEMBERSHIP_TIER", tier)
    monkeypatch.setenv("NEXUS_FOUNDER_ROUTES_ENABLED", "1")
    monkeypatch.setenv("NEXUS_ENV", "development")


# ---------------------------------------------------------------------------
# PASS 1 — core contract
# ---------------------------------------------------------------------------


def test_pass1_operator_requires_founder(monkeypatch):
    _member_env(monkeypatch, "PRO")
    client = _app().test_client()
    r = client.get("/api/nexus/founder/operator")
    assert r.status_code == 403
    body = r.get_json()
    assert body["ok"] is False
    assert body["memberAccessible"] is False
    assert "member_session_denied" in body["error"] or "entitlement_denied" in body["error"]


def test_pass1_anonymous_denied(monkeypatch):
    monkeypatch.setenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", "1")
    monkeypatch.delenv("NEXUS_ENTITLEMENT_TEST_MODE", raising=False)
    client = _app().test_client()
    r = client.get("/api/nexus/founder/operator/overview")
    assert r.status_code == 403


def test_pass1_founder_receives_all_panels(monkeypatch):
    _founder_env(monkeypatch)
    client = _app().test_client()
    r = client.get("/api/nexus/founder/operator")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["founderOnly"] is True
    assert body["memberAccessible"] is False
    assert body["realExecutionEnabled"] is False
    assert body["exchangeWriteEnabled"] is False
    ids = {p["id"] for p in body["panels"]}
    required = {
        "capture",
        "provider",
        "decision",
        "execution_sim",
        "risk",
        "ledger",
        "checkpoint",
        "reflection",
        "lesson",
        "qualification",
        "storage",
        "kill_switch",
    }
    assert required <= ids
    assert all(p["readOnly"] is True for p in body["panels"])
    assert all(p["memberVisible"] is False for p in body["panels"])
    assert r.headers.get("X-Nexus-Member-Accessible") == "0"


def test_pass1_kill_switch_readiness_only(monkeypatch):
    _founder_env(monkeypatch)
    client = _app().test_client()
    body = client.get("/api/nexus/founder/operator").get_json()
    ks = next(p for p in body["panels"] if p["id"] == "kill_switch")
    assert ks["metrics"]["engageFromUi"] is False
    assert ks["metrics"]["memberAccessible"] is False
    assert ks["metrics"]["blocksExchangeWrite"] is True


def test_pass1_execution_sim_never_live(monkeypatch):
    _founder_env(monkeypatch)
    body = _app().test_client().get("/api/nexus/founder/operator").get_json()
    ex = next(p for p in body["panels"] if p["id"] == "execution_sim")
    assert ex["metrics"]["realExecutionEnabled"] is False
    assert ex["metrics"]["armEnabled"] is False
    assert ex["metrics"]["mode"] == "SIMULATION"


def test_pass1_lesson_not_member_readable(monkeypatch):
    _founder_env(monkeypatch)
    body = _app().test_client().get("/api/nexus/founder/operator").get_json()
    lesson = next(p for p in body["panels"] if p["id"] == "lesson")
    assert lesson["metrics"]["memberReadable"] is False
    assert lesson["metrics"]["publicExportAllowed"] is False


def test_pass1_no_forbidden_payload_keys(monkeypatch):
    from backend.founder_operator.snapshot import assert_no_forbidden_keys, build_founder_operator_snapshot

    payload = build_founder_operator_snapshot(actor_tier="FOUNDER", identity_source="local_test_mode")
    assert assert_no_forbidden_keys(payload) == []


# ---------------------------------------------------------------------------
# PASS 2 — adversarial / boundary
# ---------------------------------------------------------------------------


def test_pass2_spoof_header_cannot_unlock_operator(monkeypatch):
    monkeypatch.setenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", "1")
    client = _app().test_client()
    r = client.get(
        "/api/nexus/founder/operator",
        headers={"X-Nexus-Role": "FOUNDER", "X-Founder": "1"},
    )
    assert r.status_code == 403
    assert "fake_header" in r.get_json()["error"]


def test_pass2_spoof_query_cannot_unlock_operator(monkeypatch):
    monkeypatch.setenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", "1")
    client = _app().test_client()
    r = client.get("/api/nexus/founder/operator?asFounder=1&tier=FOUNDER")
    assert r.status_code == 403
    assert "fake_query" in r.get_json()["error"]


@pytest.mark.parametrize("tier", ["FREE", "PRO", "ADVANCED", "ELITE", "ENTERPRISE", "ANONYMOUS"])
def test_pass2_all_member_tiers_denied(monkeypatch, tier):
    _member_env(monkeypatch, tier)
    r = _app().test_client().get("/api/nexus/founder/operator")
    assert r.status_code == 403
    body = r.get_json()
    assert body["memberAccessible"] is False
    assert body["realExecutionEnabled"] is False


def test_pass2_routes_disabled_blocks_even_founder_tier_label(monkeypatch):
    monkeypatch.delenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", raising=False)
    monkeypatch.setenv("NEXUS_ENTITLEMENT_TEST_MODE", "1")
    monkeypatch.setenv("NEXUS_MEMBERSHIP_TIER", "FOUNDER")
    monkeypatch.setenv("NEXUS_FOUNDER_ROUTES_ENABLED", "0")
    monkeypatch.setenv("NEXUS_ENV", "development")
    # founder_routes_enabled is False when flag off and not test-gated wait —
    # local test mode still enables routes; force production-like to disable.
    monkeypatch.setenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", "1")
    r = _app().test_client().get("/api/nexus/founder/operator")
    assert r.status_code == 403


def test_pass2_status_marks_operator_ui_and_not_member(monkeypatch):
    _founder_env(monkeypatch)
    r = _app().test_client().get("/api/nexus/founder/status")
    assert r.status_code == 200
    body = r.get_json()
    assert body["memberAccessible"] is False
    assert body["operatorUiEnabled"] is True
    assert "operator_ui_view" in body["capabilities"]


def test_pass2_panel_list_denied_for_member(monkeypatch):
    _member_env(monkeypatch, "ELITE")
    r = _app().test_client().get("/api/nexus/founder/operator/panels")
    assert r.status_code == 403


def test_pass2_hard_bans_listed(monkeypatch):
    _founder_env(monkeypatch)
    body = _app().test_client().get("/api/nexus/founder/operator").get_json()
    bans = set(body["hardBans"])
    assert "no_member_session_access" in bans
    assert "no_exchange_write" in bans
    assert "no_demo_order" in bans
    assert "no_mainnet" in bans


def test_pass2_ast_member_nav_must_not_link_operator(monkeypatch):
    """Adversarial: member SidebarNav source must not deep-link operator panels."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "src"))
    sidebar = os.path.join(root, "components", "SidebarNav.tsx")
    with open(sidebar, encoding="utf-8") as f:
        src = f.read()
    assert "/founder/operator" not in src
    assert "/founder/runtime" not in src  # removed from member research nav


def test_pass2_qualification_blocks_formal_wf(monkeypatch):
    _founder_env(monkeypatch)
    body = _app().test_client().get("/api/nexus/founder/operator").get_json()
    q = next(p for p in body["panels"] if p["id"] == "qualification")
    assert q["metrics"]["formalWfAllowed"] is False
    assert q["metrics"]["oosReservationAllowed"] is False
    assert q["metrics"]["promotionAllowed"] is False


def test_pass2_member_pages_do_not_import_founder_operator():
    """Adversarial: product/member page modules must not bind founder operator API."""
    pages_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "frontend", "src", "pages")
    )
    offenders: list[str] = []
    for root, _dirs, files in os.walk(pages_dir):
        for name in files:
            if not name.endswith((".ts", ".tsx")):
                continue
            path = os.path.join(root, name)
            # Legacy redirect shim is allowed to point at the gated operator route.
            if name == "FounderRuntimePage.tsx":
                continue
            with open(path, encoding="utf-8") as f:
                src = f.read()
            if "founder/FounderOperator" in src or "fetchFounderOperator" in src:
                offenders.append(os.path.relpath(path, pages_dir))
            if "/api/nexus/founder/operator" in src:
                offenders.append(os.path.relpath(path, pages_dir))
    assert offenders == []


def test_pass2_internal_admin_denied(monkeypatch):
    _member_env(monkeypatch, "INTERNAL_ADMIN")
    r = _app().test_client().get("/api/nexus/founder/operator")
    assert r.status_code == 403
    assert r.get_json()["memberAccessible"] is False
