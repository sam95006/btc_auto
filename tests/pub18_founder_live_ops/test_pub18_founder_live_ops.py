"""PUB18-C Founder Live Operations — contract + adversarial control tests."""
from __future__ import annotations

from flask import Flask

from backend.nexus_pub18_founder_live_ops.constants import (
    ALLOWED_CONTROLS,
    BANNED_CONTROLS,
    LIVE_OPS_PANEL_IDS,
)
from backend.nexus_pub18_founder_live_ops.hard_bans import (
    count_banned_controls_in_owned_paths,
    run_gate,
)
from backend.nexus_pub18_founder_live_ops.panels import assert_no_forbidden_keys
from backend.nexus_pub18_founder_live_ops.state import reset_state


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


def setup_function():
    reset_state()


def test_member_gets_403(monkeypatch):
    _member_env(monkeypatch, "PRO")
    r = _app().test_client().get("/api/nexus/founder/live-ops")
    assert r.status_code == 403
    body = r.get_json()
    assert body["ok"] is False
    assert body["memberAccessible"] is False
    assert body["founderOnly"] is True


def test_anonymous_denied(monkeypatch):
    monkeypatch.setenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", "1")
    monkeypatch.delenv("NEXUS_ENTITLEMENT_TEST_MODE", raising=False)
    r = _app().test_client().get("/api/nexus/founder/live-ops")
    assert r.status_code == 403


def test_founder_receives_all_live_ops_panels(monkeypatch):
    _founder_env(monkeypatch)
    r = _app().test_client().get("/api/nexus/founder/live-ops")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["schema"] == "NEXUS_FOUNDER_LIVE_OPERATIONS_PUB18_C"
    assert body["lane"] == "PUB18-C"
    assert body["founderOnly"] is True
    assert body["memberAccessible"] is False
    assert body["exchangeWriteEnabled"] is False
    assert body["mainnetShortcut"] is False
    assert body["banned_control_count"] == 0
    ids = {p["id"] for p in body["panels"]}
    assert set(LIVE_OPS_PANEL_IDS) <= ids
    assert set(body["allowedControls"]) == set(ALLOWED_CONTROLS)
    assert set(body["bannedControls"]) == set(BANNED_CONTROLS)
    assert assert_no_forbidden_keys(body) == []
    assert r.headers.get("X-Nexus-Member-Accessible") == "0"
    assert r.headers.get("X-Nexus-Banned-Control-Count") == "0"


def test_panel_list_ids_only(monkeypatch):
    _founder_env(monkeypatch)
    body = _app().test_client().get("/api/nexus/founder/live-ops/panels").get_json()
    assert body["ok"] is True
    assert set(body["panelIds"]) == set(LIVE_OPS_PANEL_IDS)
    assert body["banned_control_count"] == 0


def test_allowed_pause_resume_ingest(monkeypatch):
    _founder_env(monkeypatch)
    client = _app().test_client()
    r = client.post("/api/nexus/founder/live-ops/control", json={"control": "pause_ingest"})
    assert r.status_code == 200
    assert r.get_json()["applied"] is True
    assert r.get_json()["opsState"]["ingest_paused"] is True
    r2 = client.post("/api/nexus/founder/live-ops/control", json={"control": "resume_ingest"})
    assert r2.status_code == 200
    assert r2.get_json()["opsState"]["ingest_paused"] is False


def test_allowed_disable_provider_and_source(monkeypatch):
    _founder_env(monkeypatch)
    client = _app().test_client()
    r = client.post(
        "/api/nexus/founder/live-ops/control",
        json={"control": "disable_provider", "params": {"provider_id": "primary_chat"}},
    )
    assert r.status_code == 200
    assert "primary_chat" in r.get_json()["opsState"]["disabled_providers"]
    r2 = client.post(
        "/api/nexus/founder/live-ops/control",
        json={"control": "disable_source", "source_id": "bybit_public_v5"},
    )
    assert r2.status_code == 200
    assert "bybit_public_v5" in r2.get_json()["opsState"]["disabled_sources"]


def test_force_read_only_degraded_and_export(monkeypatch):
    _founder_env(monkeypatch)
    client = _app().test_client()
    r = client.post(
        "/api/nexus/founder/live-ops/control",
        json={"control": "force_read_only_degraded_mode"},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["opsState"]["read_only_degraded"] is True
    assert body["opsState"]["emergency_read_only_stop"] is True
    assert body["opsState"]["ingest_paused"] is True
    assert body["exchangeWriteEnabled"] is False
    ex = client.post("/api/nexus/founder/live-ops/control", json={"control": "export_evidence"})
    assert ex.status_code == 200
    export = ex.get_json()["evidenceExport"]
    assert export["banned_control_count"] == 0
    assert "evidence_export" in export["schema"]


def test_banned_controls_rejected(monkeypatch):
    _founder_env(monkeypatch)
    client = _app().test_client()
    for control in BANNED_CONTROLS:
        r = client.post("/api/nexus/founder/live-ops/control", json={"control": control})
        assert r.status_code == 403, control
        body = r.get_json()
        assert body["ok"] is False
        assert body["applied"] is False
        assert body["banned"] is True
        assert body["error"] == "banned_control"


def test_banned_control_aliases_rejected(monkeypatch):
    _founder_env(monkeypatch)
    client = _app().test_client()
    for control in ("trade now", "force LONG", "enable mainnet", "override Risk", "change leverage"):
        r = client.post("/api/nexus/founder/live-ops/control", json={"control": control})
        assert r.status_code == 403, control
        assert r.get_json()["banned"] is True


def test_member_cannot_control(monkeypatch):
    _member_env(monkeypatch, "PRO")
    r = _app().test_client().post(
        "/api/nexus/founder/live-ops/control",
        json={"control": "pause_ingest"},
    )
    assert r.status_code == 403


def test_spoof_header_rejected(monkeypatch):
    _member_env(monkeypatch, "PRO")
    r = _app().test_client().get(
        "/api/nexus/founder/live-ops",
        headers={"X-Nexus-Role": "FOUNDER"},
    )
    assert r.status_code == 403
    assert "fake_header_rejected" in r.get_json()["error"]


def test_banned_control_count_is_zero():
    scan = count_banned_controls_in_owned_paths()
    assert scan["banned_control_count"] == 0
    assert scan["ok"] is True


def test_gate_pass():
    result = run_gate()
    assert result["ok"] is True
    assert result["status"] == "PASS"
    assert result["banned_control_count"] == 0


def test_allowed_and_banned_disjoint():
    assert set(ALLOWED_CONTROLS).isdisjoint(set(BANNED_CONTROLS))
