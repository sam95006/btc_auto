"""PUB2-D Founder Operator UI live binding — three adversarial passes."""
from __future__ import annotations

import json
import os
from pathlib import Path

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
    monkeypatch.setenv("NEXUS_FOUNDER_OPERATOR_FORCE_SIMULATED", "1")


def _member_env(monkeypatch, tier: str = "PRO"):
    monkeypatch.delenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", raising=False)
    monkeypatch.setenv("NEXUS_ENTITLEMENT_TEST_MODE", "1")
    monkeypatch.setenv("NEXUS_MEMBERSHIP_TIER", tier)
    monkeypatch.setenv("NEXUS_FOUNDER_ROUTES_ENABLED", "1")
    monkeypatch.setenv("NEXUS_ENV", "development")


REQUIRED_SURFACES = {
    "capture",
    "provider",  # V2.3
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


# ---------------------------------------------------------------------------
# PASS 1 — live/sim binding contract
# ---------------------------------------------------------------------------


def test_pass1_all_surfaces_bound(monkeypatch):
    _founder_env(monkeypatch)
    from backend.founder_operator.live_bindings import bind_all_operator_surfaces

    bindings = bind_all_operator_surfaces(prefer_simulated=True)
    assert set(bindings) == REQUIRED_SURFACES
    for panel_id, binding in bindings.items():
        assert binding["mode"] in {"LIVE", "SIMULATED"}
        assert binding["fabricated"] is False
        assert binding["sourceSurface"]
        assert binding["asOf"]
        assert binding["retrievedAt"]
        assert binding["lineageId"]
        assert binding["metrics"] is not None


def test_pass1_snapshot_includes_binding_metadata(monkeypatch):
    _founder_env(monkeypatch)
    client = _app().test_client()
    r = client.get("/api/nexus/founder/operator")
    assert r.status_code == 200
    body = r.get_json()
    assert body["schema"] == "NEXUS_FOUNDER_OPERATOR_UI_V2_LIVE"
    assert body["liveBinding"] is True
    assert body["memberAccessible"] is False
    assert body["bindings"]["fabricatedLiveValueCount"] == 0
    assert body["bindings"]["memberAccessibleBindingCount"] == 0
    assert body["bindings"]["panelCount"] == 12
    for panel in body["panels"]:
        b = panel["binding"]
        assert b["mode"] in {"LIVE", "SIMULATED"}
        assert b["fabricated"] is False
        assert b["lineageId"]
        assert panel["memberVisible"] is False


def test_pass1_v23_provider_surface_labeled(monkeypatch):
    _founder_env(monkeypatch)
    body = _app().test_client().get("/api/nexus/founder/operator").get_json()
    provider = next(p for p in body["panels"] if p["id"] == "provider")
    assert "V2.3" in provider["title"]
    assert "V2.3" in provider["binding"]["sourceSurface"] or "v23" in provider["metrics"].get(
        "v23Protocol", ""
    ).lower()
    assert provider["metrics"]["v23Protocol"] == "REFLECTION_V2_3"


def test_pass1_execution_sim_hard_overlay(monkeypatch):
    _founder_env(monkeypatch)
    body = _app().test_client().get("/api/nexus/founder/operator").get_json()
    ex = next(p for p in body["panels"] if p["id"] == "execution_sim")
    assert ex["metrics"]["realExecutionEnabled"] is False
    assert ex["metrics"]["armEnabled"] is False
    assert ex["metrics"]["mode"] == "SIMULATION"


def test_pass1_live_artifact_preferred_when_present(monkeypatch, tmp_path):
    monkeypatch.delenv("NEXUS_FOUNDER_OPERATOR_FORCE_SIMULATED", raising=False)
    monkeypatch.setenv("NEXUS_RUNTIME", str(tmp_path))
    artifact = tmp_path / "capture_supervisor_health.json"
    artifact.write_text(
        json.dumps(
            {
                "health": "OK",
                "as_of": "2026-08-05T12:00:00Z",
                "process_liveness": "ALIVE",
                "ws_health": "CONNECTED",
                "hourly_partition_ok": True,
                "clock_quality": "STABLE",
            }
        ),
        encoding="utf-8",
    )
    from backend.founder_operator.live_bindings import bind_operator_surface

    binding = bind_operator_surface("capture", prefer_simulated=False)
    assert binding["mode"] == "LIVE"
    assert binding["metrics"]["processLiveness"] == "ALIVE"
    assert binding["fabricated"] is False


def test_pass1_fabricated_live_artifact_rejected(monkeypatch, tmp_path):
    monkeypatch.delenv("NEXUS_FOUNDER_OPERATOR_FORCE_SIMULATED", raising=False)
    monkeypatch.setenv("NEXUS_RUNTIME", str(tmp_path))
    (tmp_path / "capture_supervisor_health.json").write_text(
        json.dumps({"health": "OK", "fabricated": True, "process_liveness": "FAKE"}),
        encoding="utf-8",
    )
    from backend.founder_operator.live_bindings import bind_operator_surface

    binding = bind_operator_surface("capture", prefer_simulated=False)
    assert binding["mode"] == "SIMULATED"
    assert binding["metrics"]["processLiveness"] != "FAKE"


# ---------------------------------------------------------------------------
# PASS 2 — auth denial + member isolation
# ---------------------------------------------------------------------------


def test_pass2_member_session_403(monkeypatch):
    _member_env(monkeypatch, "PRO")
    r = _app().test_client().get("/api/nexus/founder/operator")
    assert r.status_code == 403
    body = r.get_json()
    assert body["ok"] is False
    assert body["memberAccessible"] is False
    assert "member_session_denied" in body["error"] or "entitlement_denied" in body["error"]


@pytest.mark.parametrize("tier", ["FREE", "PRO", "ADVANCED", "ELITE", "ENTERPRISE", "ANONYMOUS", "INTERNAL_ADMIN"])
def test_pass2_all_non_founder_tiers_denied(monkeypatch, tier):
    _member_env(monkeypatch, tier)
    r = _app().test_client().get("/api/nexus/founder/operator")
    assert r.status_code == 403
    assert r.get_json()["memberAccessible"] is False


def test_pass2_spoof_header_denied(monkeypatch):
    monkeypatch.setenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", "1")
    r = _app().test_client().get(
        "/api/nexus/founder/operator",
        headers={"X-Nexus-Role": "FOUNDER", "X-Founder": "1"},
    )
    assert r.status_code == 403
    assert "fake_header" in r.get_json()["error"]


def test_pass2_panels_route_member_denied(monkeypatch):
    _member_env(monkeypatch, "ELITE")
    r = _app().test_client().get("/api/nexus/founder/operator/panels")
    assert r.status_code == 403


def test_pass2_no_forbidden_keys_in_live_snapshot(monkeypatch):
    _founder_env(monkeypatch)
    from backend.founder_operator.snapshot import assert_no_forbidden_keys, build_founder_operator_snapshot

    payload = build_founder_operator_snapshot(
        actor_tier="FOUNDER",
        identity_source="local_test_mode",
        prefer_simulated=True,
    )
    assert assert_no_forbidden_keys(payload) == []


def test_pass2_member_paths_do_not_import_founder_operator():
    from backend.founder_operator.hard_bans import scan_member_paths_for_founder_imports

    result = scan_member_paths_for_founder_imports()
    assert result["ok"] is True, result["hits"]


def test_pass2_member_paths_have_no_secret_literals():
    from backend.founder_operator.hard_bans import scan_member_paths_for_secret_literals

    result = scan_member_paths_for_secret_literals()
    assert result["ok"] is True, result["hits"]


# ---------------------------------------------------------------------------
# PASS 3 — independent break attempts + hard bans
# ---------------------------------------------------------------------------


def test_pass3_hard_ban_three_passes():
    from backend.founder_operator.hard_bans import run_three_passes

    result = run_three_passes()
    assert result["ok"] is True
    assert result["pass_count"] == 3
    assert all(p["ok"] for p in result["passes"])


def test_pass3_query_spoof_denied(monkeypatch):
    monkeypatch.setenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", "1")
    r = _app().test_client().get("/api/nexus/founder/operator?asFounder=1&tier=FOUNDER")
    assert r.status_code == 403
    assert "fake_query" in r.get_json()["error"]


def test_pass3_lesson_never_member_readable(monkeypatch):
    _founder_env(monkeypatch)
    body = _app().test_client().get("/api/nexus/founder/operator").get_json()
    lesson = next(p for p in body["panels"] if p["id"] == "lesson")
    assert lesson["metrics"]["memberReadable"] is False
    assert lesson["metrics"]["publicExportAllowed"] is False
    assert lesson["memberVisible"] is False


def test_pass3_kill_switch_cannot_engage_from_ui(monkeypatch):
    _founder_env(monkeypatch)
    body = _app().test_client().get("/api/nexus/founder/operator").get_json()
    ks = next(p for p in body["panels"] if p["id"] == "kill_switch")
    assert ks["metrics"]["engageFromUi"] is False
    assert ks["metrics"]["memberAccessible"] is False


def test_pass3_qualification_blocks_formal_wf(monkeypatch):
    _founder_env(monkeypatch)
    body = _app().test_client().get("/api/nexus/founder/operator").get_json()
    q = next(p for p in body["panels"] if p["id"] == "qualification")
    assert q["metrics"]["formalWfAllowed"] is False
    assert q["metrics"]["oosReservationAllowed"] is False
    assert q["metrics"]["promotionAllowed"] is False


def test_pass3_frontend_member_pages_exclude_founder_api():
    pages = Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages"
    offenders: list[str] = []
    for path in pages.rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        if path.name == "FounderRuntimePage.tsx":
            continue
        src = path.read_text(encoding="utf-8")
        if "/api/nexus/founder/operator" in src or "fetchFounderOperator" in src:
            offenders.append(str(path.relative_to(pages)))
        if "founder/FounderOperator" in src and "member" in str(path).lower():
            offenders.append(str(path.relative_to(pages)))
    assert offenders == []


def test_pass3_simulated_fixture_not_claimed_live(monkeypatch):
    _founder_env(monkeypatch)
    from backend.founder_operator.live_bindings import bind_all_operator_surfaces

    bindings = bind_all_operator_surfaces(prefer_simulated=True)
    assert all(b["mode"] == "SIMULATED" for b in bindings.values())
    assert all(b["fabricated"] is False for b in bindings.values())
