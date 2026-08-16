"""Safe alpha HTTP/event integration tests on the authoritative Flask framework."""
from __future__ import annotations

from flask import Flask

from backend.nexus_product_backend.routes import register_product_alpha_routes
from backend.nexus_public_realtime_transport.routes import (
    register_public_realtime_routes,
    reset_hub_for_tests,
)


def _app() -> Flask:
    app = Flask(__name__)
    app.testing = True
    reset_hub_for_tests()
    register_product_alpha_routes(app)
    register_public_realtime_routes(app)
    return app


def test_safe_foundation_and_read_model_routes():
    client = _app().test_client()
    foundation = client.get("/api/v1/product/auth/foundation")
    assert foundation.status_code == 200
    assert foundation.get_json()["password_hashing"] == "argon2"
    capabilities = client.get("/api/v1/product/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.get_json()["validation"]["ok"] is True
    market = client.get("/api/v1/product/market-overview")
    assert market.status_code == 200
    assert market.get_json()["execution_controls"] is False
    assert market.get_json()["credentials_exposed"] is False


def test_runtime_event_emits_versioned_envelope_and_publishes_to_hub():
    client = _app().test_client()
    response = client.get("/api/v1/product/events/runtime-health")
    assert response.status_code == 200
    envelope = response.get_json()
    assert envelope["schema"] == "v18_3_3_event_contract_v1"
    assert envelope["event_type"] == "runtime.health"
    assert envelope["event_id"]
    assert envelope["reconnect_cursor"]
    assert envelope["dedupe_key"] == envelope["event_id"]
    poll = client.get("/api/public/v1/realtime/poll")
    assert poll.status_code == 200
    events = poll.get_json().get("events") or []
    assert any(evt.get("kind") == "freshness_change" for evt in events)


def test_protected_routes_fail_closed_without_injected_services():
    client = _app().test_client()
    response = client.post(
        "/api/v1/product/entitlement/check",
        json={"capability_id": "MARKET_OVERVIEW"},
    )
    assert response.status_code == 401
    assert response.get_json()["allowed"] is False
