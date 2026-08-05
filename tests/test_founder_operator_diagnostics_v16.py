"""UX-C Founder Operator Diagnostics — three adversarial passes."""
from __future__ import annotations

from flask import Flask

from backend.founder_operator.diagnostics.panels import DIAGNOSTIC_PANEL_IDS
from backend.founder_operator.diagnostics.three_pass import run_three_passes


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


REQUIRED_PANELS = set(DIAGNOSTIC_PANEL_IDS)


# ---------------------------------------------------------------------------
# PASS 1 — core contract
# ---------------------------------------------------------------------------


def test_pass1_member_gets_403(monkeypatch):
    _member_env(monkeypatch, "PRO")
    r = _app().test_client().get("/api/nexus/founder/diagnostics")
    assert r.status_code == 403
    body = r.get_json()
    assert body["ok"] is False
    assert body["memberAccessible"] is False
    assert body["founderOnly"] is True


def test_pass1_free_member_denied(monkeypatch):
    _member_env(monkeypatch, "FREE")
    r = _app().test_client().get("/api/nexus/founder/diagnostics/overview")
    assert r.status_code == 403


def test_pass1_anonymous_denied(monkeypatch):
    monkeypatch.setenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", "1")
    monkeypatch.delenv("NEXUS_ENTITLEMENT_TEST_MODE", raising=False)
    r = _app().test_client().get("/api/nexus/founder/diagnostics")
    assert r.status_code == 403


def test_pass1_founder_receives_all_diagnostic_panels(monkeypatch):
    _founder_env(monkeypatch)
    r = _app().test_client().get("/api/nexus/founder/diagnostics")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["schema"] == "NEXUS_FOUNDER_OPERATOR_DIAGNOSTICS_V16"
    assert body["lane"] == "UX-C"
    assert body["founderOnly"] is True
    assert body["memberAccessible"] is False
    assert body["researchOnly"] is True
    assert body["observeOnly"] is True
    assert body["authorizeResearchOnly"] is True
    assert body["realExecutionEnabled"] is False
    assert body["exchangeWriteEnabled"] is False
    assert body["mainnetShortcut"] is False
    assert body["realTradeShortcut"] is False
    assert body["statusJsonReport"] is False
    ids = {p["id"] for p in body["panels"]}
    assert REQUIRED_PANELS <= ids
    assert all(p["readOnly"] is True for p in body["panels"])
    assert all(p["memberVisible"] is False for p in body["panels"])
    assert r.headers.get("X-Nexus-Member-Accessible") == "0"
    assert r.headers.get("X-Nexus-Research-Only") == "1"


def test_pass1_panel_list_ids_only(monkeypatch):
    _founder_env(monkeypatch)
    body = _app().test_client().get("/api/nexus/founder/diagnostics/panels").get_json()
    assert body["ok"] is True
    assert set(body["panelIds"]) == REQUIRED_PANELS
    assert "panels" not in body


# ---------------------------------------------------------------------------
# PASS 2 — adversarial authorize + shortcuts
# ---------------------------------------------------------------------------


def test_pass2_spoof_header_rejected(monkeypatch):
    _member_env(monkeypatch, "PRO")
    r = _app().test_client().get(
        "/api/nexus/founder/diagnostics",
        headers={"X-Nexus-Role": "FOUNDER"},
    )
    assert r.status_code == 403
    assert "fake_header_rejected" in r.get_json()["error"]


def test_pass2_spoof_query_rejected(monkeypatch):
    _founder_env(monkeypatch)
    r = _app().test_client().get("/api/nexus/founder/diagnostics?tier=FOUNDER")
    assert r.status_code == 403
    assert "fake_query_rejected" in r.get_json()["error"]


def test_pass2_research_authorize_observe_ok(monkeypatch):
    _founder_env(monkeypatch)
    r = _app().test_client().post(
        "/api/nexus/founder/diagnostics/research-authorize",
        json={"researchOnly": True, "scope": "observe_diagnostics"},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["authorized"] is True
    assert body["realExecutionEnabled"] is False
    assert body["exchangeWriteEnabled"] is False
    assert body["mainnetShortcut"] is False
    assert body["realTradeShortcut"] is False


def test_pass2_research_authorize_requires_flag(monkeypatch):
    _founder_env(monkeypatch)
    r = _app().test_client().post(
        "/api/nexus/founder/diagnostics/research-authorize",
        json={"scope": "observe_diagnostics"},
    )
    assert r.status_code == 400


def test_pass2_mainnet_scope_denied(monkeypatch):
    _founder_env(monkeypatch)
    r = _app().test_client().post(
        "/api/nexus/founder/diagnostics/research-authorize",
        json={"researchOnly": True, "scope": "mainnet"},
    )
    assert r.status_code == 403
    body = r.get_json()
    assert body["authorized"] is False
    assert "forbidden_scope" in body["error"]


def test_pass2_real_trade_scope_denied(monkeypatch):
    _founder_env(monkeypatch)
    for scope in ("real_trade", "exchange_write", "arm_execution", "demo_order"):
        r = _app().test_client().post(
            "/api/nexus/founder/diagnostics/research-authorize",
            json={"researchOnly": True, "scope": scope},
        )
        assert r.status_code == 403, scope
        assert r.get_json()["authorized"] is False


def test_pass2_member_cannot_authorize_research(monkeypatch):
    _member_env(monkeypatch, "PRO")
    r = _app().test_client().post(
        "/api/nexus/founder/diagnostics/research-authorize",
        json={"researchOnly": True, "scope": "observe_diagnostics"},
    )
    assert r.status_code == 403


def test_pass2_router_and_lesson_fail_closed(monkeypatch):
    _founder_env(monkeypatch)
    body = _app().test_client().get("/api/nexus/founder/diagnostics").get_json()
    router = next(p for p in body["panels"] if p["id"] == "strategy_router_weights")
    lesson = next(p for p in body["panels"] if p["id"] == "lesson_pipeline")
    portfolio = next(p for p in body["panels"] if p["id"] == "portfolio_risk")
    assert router["metrics"]["noTradeFirstClass"] is True
    assert router["metrics"]["mainnetShortcut"] is False
    assert lesson["metrics"]["activeBlocked"] is True
    assert lesson["metrics"]["realLessonActive"] is False
    assert portfolio["metrics"]["openRealPositions"] == 0
    assert portfolio["metrics"]["observeOnly"] is True


def test_pass2_no_forbidden_payload_keys(monkeypatch):
    _founder_env(monkeypatch)
    from backend.founder_operator.diagnostics.panels import assert_no_forbidden_keys

    body = _app().test_client().get("/api/nexus/founder/diagnostics").get_json()
    assert assert_no_forbidden_keys(body) == []


# ---------------------------------------------------------------------------
# PASS 3 — hard bans + three_pass runner
# ---------------------------------------------------------------------------


def test_pass3_three_passes_ok():
    result = run_three_passes()
    assert result["pass_count"] == 3
    assert result["status_json_report"] is False
    assert result["ok"] is True, result
    assert all(p["ok"] for p in result["passes"]), result["passes"]


def test_pass3_hard_ban_list_present(monkeypatch):
    _founder_env(monkeypatch)
    body = _app().test_client().get("/api/nexus/founder/diagnostics").get_json()
    bans = set(body["hardBans"])
    for required in (
        "no_mainnet",
        "no_real_money",
        "no_exchange_write",
        "no_member_session_access",
        "no_mainnet_shortcut",
        "no_real_trade_shortcut",
        "no_status_json_report",
        "observe_authorize_research_only",
    ):
        assert required in bans


def test_pass3_v16_module_versions_panel(monkeypatch):
    _founder_env(monkeypatch)
    body = _app().test_client().get("/api/nexus/founder/diagnostics").get_json()
    versions = next(p for p in body["panels"] if p["id"] == "v16_module_versions")
    assert versions["metrics"]["moduleCount"] == 8
    assert versions["metrics"]["privateCoreImport"] is False
    assert versions["metrics"]["integrationStatus"] == "PROJECTION_ONLY"
    lanes = {m["lane"] for m in versions["metrics"]["modules"]}
    assert lanes == {"V16-A", "V16-B", "V16-C", "V16-D", "V16-E", "V16-F", "V16-G", "V16-H"}


def test_pass3_frontend_diagnostics_surface_exists():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    page = root / "frontend" / "src" / "founder" / "FounderDiagnosticsPage.tsx"
    app = root / "frontend" / "src" / "App.tsx"
    assert page.is_file()
    app_src = app.read_text(encoding="utf-8")
    assert "/founder/diagnostics" in app_src
    assert "FounderDiagnosticsPage" in app_src
    page_src = page.read_text(encoding="utf-8")
    assert "memberVisible=false" in page_src or "memberVisible={String" in page_src
    assert "observe_diagnostics" in page_src
