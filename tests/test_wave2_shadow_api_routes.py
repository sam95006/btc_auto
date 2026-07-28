"""Wave 2 shadow API route registration and coverage tests."""
from __future__ import annotations

import pytest
from flask import Flask

from backend.nexus_global_shadow.api_routes import (
    EMPTY_FUNNEL,
    FIXTURE_LABELS,
    READ_ONLY_META,
    dispatch_route,
    enable_explicit_fixture_mode,
    register_shadow_routes,
    reset_shadow_api_state,
)


@pytest.fixture
def shadow_app():
    reset_shadow_api_state()
    app = Flask(__name__)
    register_shadow_routes(app)
    return app


@pytest.fixture
def client(shadow_app):
    return shadow_app.test_client()


class TestShadowApiDispatch:
    def setup_method(self):
        reset_shadow_api_state()

    def test_all_static_routes_read_only_meta(self):
        paths = [
            "/api/nexus/shadow/overview",
            "/api/nexus/shadow/universe",
            "/api/nexus/shadow/universe/latest",
            "/api/nexus/shadow/markets",
            "/api/nexus/shadow/candidates",
            "/api/nexus/shadow/reviews",
            "/api/nexus/shadow/risk-verdicts",
            "/api/nexus/shadow/portfolio",
            "/api/nexus/shadow/positions",
            "/api/nexus/shadow/outcomes",
            "/api/nexus/shadow/reflections",
            "/api/nexus/shadow/learning-patches",
            "/api/nexus/shadow/replay/status",
            "/api/nexus/shadow/workers/health",
        ]
        for path in paths:
            out = dispatch_route(path)
            assert out["read_only"] is True
            assert out["exchange_write"] is False
            assert out["mainnet"] is False
            assert out["real_money"] is False
            assert "SHADOW" in out["labels"]
            assert "NO_EXCHANGE_WRITE" in out["labels"]

    def test_product_overview_is_no_data_not_synthetic(self):
        out = dispatch_route("/api/nexus/shadow/overview")
        assert out["data_status"] == "NO_DATA"
        assert out["data_source"] == "NONE"
        assert out["funnel"] == EMPTY_FUNNEL
        assert out["funnel"]["marketsScanned"] == 0
        assert out["freshness"] == "UNAVAILABLE"
        assert out["providerStatus"] == "NOT_CONNECTED"
        assert "FIXTURE" not in out["labels"]
        assert "SYNTHETIC_TEST_DATA" not in out["labels"]

    def test_fixture_only_when_explicit(self):
        enable_explicit_fixture_mode(True)
        out = dispatch_route("/api/nexus/shadow/overview")
        assert out["data_status"] == "FIXTURE"
        assert out["funnel"]["marketsScanned"] == 128
        for label in FIXTURE_LABELS:
            assert label in out["labels"]

        dedicated = dispatch_route("/api/nexus/shadow/fixture/overview")
        assert dedicated["data_status"] == "FIXTURE"
        assert "SYNTHETIC_TEST_DATA" in dedicated["labels"]

    def test_param_routes_no_default_fixture(self):
        out = dispatch_route("/api/nexus/shadow/markets/BTCUSDT")
        assert out.get("ok") is False
        assert out["error"] == "not_found"
        assert out["data_status"] == "NO_DATA"

        out = dispatch_route("/api/nexus/shadow/candidates/fixture_cand_001")
        assert out.get("ok") is False
        assert out["data_status"] == "NO_DATA"

        enable_explicit_fixture_mode(True)
        out = dispatch_route("/api/nexus/shadow/candidates/fixture_cand_001")
        assert out["candidate"]["candidate_id"] == "fixture_cand_001"
        assert "SYNTHETIC_TEST_DATA" in out["labels"]

        out = dispatch_route("/api/nexus/shadow/evidence/fixture_evidence_001")
        assert out["evidence"]["record_id"] == "fixture_evidence_001"

    def test_unknown_route(self):
        out = dispatch_route("/api/nexus/shadow/unknown")
        assert out["error"] == "unknown_route"


class TestShadowFlaskRoutes:
    def setup_method(self):
        reset_shadow_api_state()

    def test_overview_endpoint(self, client):
        res = client.get("/api/nexus/shadow/overview")
        assert res.status_code == 200
        data = res.get_json()
        assert data["read_only"] is True
        assert data["data_status"] == "NO_DATA"
        assert data["funnel"]["marketsScanned"] == 0
        assert data["maxOpenPositions"] == 2

    def test_fixture_overview_endpoint(self, client):
        res = client.get("/api/nexus/shadow/fixture/overview")
        assert res.status_code == 200
        data = res.get_json()
        assert data["data_status"] == "FIXTURE"
        assert data["funnel"]["marketsScanned"] == 128
        assert "SYNTHETIC_TEST_DATA" in data["labels"]

    def test_universe_endpoints(self, client):
        res = client.get("/api/nexus/shadow/universe")
        assert res.status_code == 200
        body = res.get_json()
        assert body["count"] == 0
        assert body["data_status"] == "NO_DATA"

        res = client.get("/api/nexus/shadow/universe/latest")
        assert res.status_code == 200
        latest = res.get_json()
        assert latest["totalMarkets"] == 0
        assert latest["providerStatus"] == "NOT_CONNECTED"

    def test_markets_endpoints(self, client):
        res = client.get("/api/nexus/shadow/markets")
        assert res.status_code == 200
        assert res.get_json()["count"] == 0

        res = client.get("/api/nexus/shadow/markets/BTCUSDT")
        assert res.status_code == 200
        assert res.get_json()["error"] == "not_found"

    def test_candidates_reviews_risk(self, client):
        res = client.get("/api/nexus/shadow/candidates")
        assert res.status_code == 200
        assert res.get_json()["count"] == 0

        res = client.get("/api/nexus/shadow/candidates/fixture_cand_001")
        assert res.status_code == 200
        assert res.get_json()["error"] == "not_found"

        res = client.get("/api/nexus/shadow/reviews")
        assert res.status_code == 200
        assert res.get_json()["count"] == 0

        res = client.get("/api/nexus/shadow/risk-verdicts")
        assert res.status_code == 200
        assert res.get_json()["count"] == 0

    def test_portfolio_positions_outcomes(self, client):
        res = client.get("/api/nexus/shadow/portfolio")
        assert res.status_code == 200
        data = res.get_json()
        assert data["maxOpenPositions"] == 2
        assert data["count"] == 0
        assert data["data_status"] == "NO_DATA"

        res = client.get("/api/nexus/shadow/positions")
        assert res.status_code == 200

        res = client.get("/api/nexus/shadow/outcomes")
        assert res.status_code == 200
        assert res.get_json()["count"] == 0

    def test_replay_evidence_workers(self, client):
        res = client.get("/api/nexus/shadow/replay/status")
        assert res.status_code == 200

        res = client.get("/api/nexus/shadow/evidence/fixture_evidence_001")
        assert res.status_code == 200
        assert res.get_json()["error"] == "not_found"

        res = client.get("/api/nexus/shadow/workers/health")
        assert res.status_code == 200
        assert len(res.get_json()["workers"]) >= 1

    def test_read_only_meta_constant(self):
        assert READ_ONLY_META["read_only"] is True
        assert READ_ONLY_META["exchange_write"] is False
        assert "FIXTURE" not in READ_ONLY_META["labels"]
