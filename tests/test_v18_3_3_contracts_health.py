"""V18.3.3 API/event contracts and composed health tests."""
from __future__ import annotations

from backend.nexus_api_contract import validate_contract as validate_api
from backend.nexus_event_contract import event_envelope, validate_contract as validate_events
from backend.nexus_product_health import compose_health, compose_readiness


def test_api_contract_alpha_pass():
    result = validate_api()
    assert result["ok"] is True
    assert result["contract"]["execution_controls_mapped"] is False


def test_event_contract_alpha_pass():
    result = validate_events()
    assert result["ok"] is True
    env = event_envelope(
        event_id="evt_1",
        event_type="runtime.health",
        occurred_at="2026-08-14T08:00:00Z",
        sequence=1,
        payload={"status": "OK"},
    )
    assert env["reconnect_cursor"] == "1:evt_1"


def test_compose_health_readonly_shadow_fields():
    health = compose_health()
    assert health["application"]["live_trading_wired"] is False
    assert "shadow_readonly" in health
    readiness = compose_readiness()
    assert "ready" in readiness
    assert "checks" in readiness
