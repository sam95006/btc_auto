"""Tests for PUB-B Public Decision Cloud read-only service."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.nexus_public_decision_cloud.constants import HARD_BANS, SURFACES
from backend.nexus_public_decision_cloud.hard_bans import (
    HardBanViolation,
    refuse_customer_trading,
    refuse_exchange_api,
    refuse_order_placement,
    refuse_private_core_import,
    run_two_passes,
)
from backend.nexus_public_decision_cloud.routes import register_public_decision_cloud_routes
from backend.nexus_public_decision_cloud.sanitize import ForbiddenPayloadKeyError, assert_no_forbidden_keys
from backend.nexus_public_decision_cloud import service

ROOT = Path(__file__).resolve().parents[1]


def test_surfaces_cover_directive():
    required = {
        "market_overview",
        "decision_feed",
        "decision_detail",
        "evidence",
        "counter_evidence",
        "risk",
        "thesis_monitor",
        "decision_memory",
        "outcome_review",
        "alerts",
        "freshness",
    }
    assert required.issubset(set(SURFACES))


def test_market_overview_is_fixture_only():
    body = service.market_overview()
    assert body["ok"] is True
    assert body["exchange_api_used"] is False
    assert body["customer_trading"] is False
    assert body["market_overview"]["exchange_api_used"] is False
    assert body["market_overview"]["source"] == "STAGING_FIXTURE"


def test_decision_feed_and_detail():
    feed = service.decision_feed()
    assert feed["count"] >= 1
    decision_id = feed["decisions"][0]["decision_id"]
    detail = service.decision_detail(decision_id)
    assert detail["ok"] is True
    assert detail["decision"]["decision"]["places_orders"] is False


def test_evidence_counter_evidence_risk():
    feed = service.decision_feed()
    decision_id = feed["decisions"][0]["decision_id"]
    ev = service.evidence_for(decision_id)
    cev = service.counter_evidence_for(decision_id)
    risk = service.risk_for(decision_id)
    assert ev["ok"] and cev["ok"] and risk["ok"]
    assert risk["advisory_only"] is True


def test_thesis_monitor_memory_outcome_alerts_freshness():
    assert service.thesis_monitor()["auto_trades"] is False
    mem = service.decision_memory()
    assert mem["private_lesson_memory"] is False
    assert all(item.get("private_lesson_memory") is False for item in mem["memory"])
    reviews = service.outcome_review()
    assert reviews["count"] >= 1
    alerts = service.alerts()
    assert all(a.get("actionable_trade") is False for a in alerts["alerts"])
    fresh = service.freshness_report()
    assert "thresholds" in fresh and fresh["items"]


def test_sanitize_blocks_secrets():
    with pytest.raises(ForbiddenPayloadKeyError):
        assert_no_forbidden_keys({"api_key": "x"})


def test_hard_ban_refusers():
    with pytest.raises(HardBanViolation):
        refuse_customer_trading()
    with pytest.raises(HardBanViolation):
        refuse_exchange_api()
    with pytest.raises(HardBanViolation):
        refuse_private_core_import()
    with pytest.raises(HardBanViolation):
        refuse_order_placement()


def test_hard_ban_two_passes():
    result = run_two_passes(ROOT)
    assert result["pass_count"] == 2
    assert result["ok"] is True
    assert result["hard_bans_intact"] is True
    assert len(result["passes"]) == 2
    assert result["passes"][0]["pass_number"] == 1
    assert result["passes"][1]["pass_number"] == 2
    assert set(HARD_BANS).issubset(set(result["passes"][0]["hard_bans"]))


def test_flask_routes_read_only():
    flask = pytest.importorskip("flask")
    app = flask.Flask("test_decision_cloud")
    register_public_decision_cloud_routes(app)
    client = app.test_client()

    meta = client.get("/api/public/decision-cloud/meta")
    assert meta.status_code == 200
    payload = meta.get_json()
    assert payload["read_only"] is True
    assert payload["exchange_api_used"] is False

    overview = client.get("/api/public/decision-cloud/market-overview")
    assert overview.status_code == 200
    assert overview.get_json()["market_overview"]["source"] == "STAGING_FIXTURE"

    feed = client.get("/api/public/decision-cloud/decisions")
    assert feed.status_code == 200
    decision_id = feed.get_json()["decisions"][0]["decision_id"]

    for path in (
        f"/api/public/decision-cloud/decisions/{decision_id}",
        f"/api/public/decision-cloud/decisions/{decision_id}/evidence",
        f"/api/public/decision-cloud/decisions/{decision_id}/counter-evidence",
        f"/api/public/decision-cloud/decisions/{decision_id}/risk",
        "/api/public/decision-cloud/thesis-monitor",
        "/api/public/decision-cloud/decision-memory",
        "/api/public/decision-cloud/outcome-review",
        "/api/public/decision-cloud/alerts",
        "/api/public/decision-cloud/freshness",
    ):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert resp.headers.get("X-NEXUS-Customer-Trading") == "false"
        assert resp.headers.get("X-NEXUS-Exchange-API") == "false"

    banned = client.post("/api/public/decision-cloud/decisions", json={"x": 1})
    assert banned.status_code == 405
    assert banned.get_json()["customer_trading"] is False


def test_no_status_json_artifacts_in_owned_tree():
    owned = ROOT / "backend" / "nexus_public_decision_cloud"
    offenders = list(owned.rglob("*_status.json"))
    assert offenders == []


def test_fixture_catalog_parseable():
    path = ROOT / "backend" / "nexus_public_decision_cloud" / "fixtures" / "staging_catalog.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["read_only"] is True
    assert data["market_overview"]["exchange_api_used"] is False
