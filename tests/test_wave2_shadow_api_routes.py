"""Wave 2 shadow API route registration and coverage tests."""
from __future__ import annotations

import pytest
from flask import Flask

from backend.nexus_global_shadow.api_routes import (
    FIXTURE_LABELS,
    READ_ONLY_META,
    dispatch_route,
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
            for label in FIXTURE_LABELS:
                assert label in out["labels"]

    def test_param_routes(self):
        out = dispatch_route("/api/nexus/shadow/markets/BTCUSDT")
        assert out["market"]["symbol"] == "BTCUSDT"

        out = dispatch_route("/api/nexus/shadow/candidates/fixture_cand_001")
        assert out["candidate"]["candidate_id"] == "fixture_cand_001"

        out = dispatch_route("/api/nexus/shadow/reviews/fixture_cand_001")
        assert out["review"]["candidate_id"] == "fixture_cand_001"

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
        assert "funnel" in data
        assert data["maxOpenPositions"] == 2

    def test_universe_endpoints(self, client):
        res = client.get("/api/nexus/shadow/universe")
        assert res.status_code == 200
        assert res.get_json()["count"] >= 1

        res = client.get("/api/nexus/shadow/universe/latest")
        assert res.status_code == 200
        assert "totalMarkets" in res.get_json()

    def test_markets_endpoints(self, client):
        res = client.get("/api/nexus/shadow/markets")
        assert res.status_code == 200
        assert res.get_json()["count"] >= 1

        res = client.get("/api/nexus/shadow/markets/BTCUSDT")
        assert res.status_code == 200
        assert res.get_json()["symbol"] == "BTCUSDT"

    def test_candidates_reviews_risk(self, client):
        res = client.get("/api/nexus/shadow/candidates")
        assert res.status_code == 200

        res = client.get("/api/nexus/shadow/candidates/fixture_cand_001")
        assert res.status_code == 200

        res = client.get("/api/nexus/shadow/reviews")
        assert res.status_code == 200

        res = client.get("/api/nexus/shadow/reviews/fixture_cand_001")
        assert res.status_code == 200

        res = client.get("/api/nexus/shadow/risk-verdicts")
        assert res.status_code == 200

    def test_portfolio_positions_outcomes(self, client):
        res = client.get("/api/nexus/shadow/portfolio")
        assert res.status_code == 200
        assert res.get_json()["maxOpenPositions"] == 2

        res = client.get("/api/nexus/shadow/positions")
        assert res.status_code == 200

        res = client.get("/api/nexus/shadow/outcomes")
        assert res.status_code == 200

        res = client.get("/api/nexus/shadow/reflections")
        assert res.status_code == 200

        res = client.get("/api/nexus/shadow/learning-patches")
        assert res.status_code == 200

    def test_replay_evidence_workers(self, client):
        res = client.get("/api/nexus/shadow/replay/status")
        assert res.status_code == 200

        res = client.get("/api/nexus/shadow/evidence/fixture_evidence_001")
        assert res.status_code == 200

        res = client.get("/api/nexus/shadow/workers/health")
        assert res.status_code == 200
        assert len(res.get_json()["workers"]) >= 1

    def test_read_only_meta_constant(self):
        assert READ_ONLY_META["read_only"] is True
        assert READ_ONLY_META["exchange_write"] is False
