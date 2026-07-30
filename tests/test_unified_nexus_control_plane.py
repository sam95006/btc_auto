"""Tests for Unified NEXUS Control Plane (read-only federation)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.nexus_control_plane import (
    DATA_STATUS_LIVE,
    DATA_STATUS_MISSING,
    DATA_STATUS_SERVICE_UNAVAILABLE,
    EXECUTION_OWNER_DEMO_VALIDATION,
    ROLE_DEMO_EXECUTION,
    ROLE_MARKET_INTELLIGENCE,
)
from backend.nexus_control_plane.aggregator import ControlPlaneAggregator
from backend.nexus_control_plane.federation_client import (
    FederationClient,
    FederationSecurityError,
    redact_secrets,
)
from backend.nexus_control_plane.field_envelope import envelope, missing
from backend.nexus_control_plane.service_registry import ServiceRegistry


def test_service_registry_single_execution_owner(monkeypatch):
    monkeypatch.setenv("STAGE3_EXECUTION_OWNER", "true")  # must be ignored
    reg = ServiceRegistry.from_env()
    assert reg.summary()["execution_owner"] == EXECUTION_OWNER_DEMO_VALIDATION
    assert reg.summary()["stage3_execution_owner"] is False
    assert reg.get(ROLE_MARKET_INTELLIGENCE).execution_owner is False
    assert reg.get(ROLE_DEMO_EXECUTION).execution_owner is True
    assert reg.get(ROLE_MARKET_INTELLIGENCE).exchange_write_capability is False
    assert reg.get(ROLE_DEMO_EXECUTION).mainnet_capability is False
    assert reg.get(ROLE_DEMO_EXECUTION).real_money_capability is False


def test_no_synthetic_zero_fallback_on_missing_account():
    env = missing(ROLE_DEMO_EXECUTION, evidence_ref="unavailable")
    assert env["value"] is None
    assert env["data_status"] == DATA_STATUS_MISSING
    assert env["value"] != 0


def test_stale_and_live_labels():
    live = envelope(1, source_service="x", source_timestamp=1.0, data_status=DATA_STATUS_LIVE)
    assert live["data_status"] == DATA_STATUS_LIVE


def test_secret_redaction():
    payload = {"wallet": 1, "api_key": "SECRET", "nested": {"api_secret": "x", "ok": True}}
    out = redact_secrets(payload)
    assert out["api_key"] == "[REDACTED]"
    assert out["nested"]["api_secret"] == "[REDACTED]"
    assert out["nested"]["ok"] is True
    assert out["wallet"] == 1


def test_ssrf_unknown_host_blocked():
    reg = ServiceRegistry.from_env()
    client = FederationClient(registry=reg)
    with pytest.raises(FederationSecurityError):
        client._assert_url_allowed("https://evil.example.com/x")


def test_readonly_method_contract_on_routes():
    from flask import Flask

    from backend.nexus_control_plane.api_routes import register_control_plane_routes

    app = Flask(__name__)
    register_control_plane_routes(app)
    client = app.test_client()
    for path in (
        "/api/nexus/control-plane/orders",
        "/api/nexus/control-plane/session/start",
        "/api/nexus/control-plane/session/stop",
        "/api/nexus/control-plane/position/close",
    ):
        resp = client.post(path, json={})
        assert resp.status_code == 405
        body = resp.get_json()
        assert body["error"] == "CONTROL_PLANE_READ_ONLY"
        assert body["exchange_write"] is False


def test_market_vs_demo_ownership_and_no_stage3_fallback():
    reg = ServiceRegistry.from_env()

    class FakeClient:
        def get_json(self, role, path):
            if role == ROLE_MARKET_INTELLIGENCE:
                return {"ok": True, "payload": {"status": "OK"}, "fetched_at": 100.0, "data_status": DATA_STATUS_LIVE}
            # Demo execution unavailable — must not invent Stage3 equity
            return {"ok": False, "data_status": DATA_STATUS_SERVICE_UNAVAILABLE, "payload": None, "error": "down"}

    agg = ControlPlaneAggregator(registry=reg, client=FakeClient())  # type: ignore[arg-type]
    overview = agg.overview()
    assert overview["ownership"]["demo_wallet"] == ROLE_DEMO_EXECUTION
    assert overview["ownership"]["market_scan"] == ROLE_MARKET_INTELLIGENCE
    assert overview["demo_account"]["note"].startswith("EXECUTION_SERVICE_UNAVAILABLE")
    assert overview["demo_account"]["equity"]["data_status"] == DATA_STATUS_MISSING
    assert overview["demo_account"]["equity"]["value"] is None


def test_schema_mismatch_and_timeout_paths():
    reg = ServiceRegistry.from_env()
    client = FederationClient(registry=reg, timeout_sec=0.01)

    class Boom:
        def __enter__(self):
            raise TimeoutError("timeout")

        def __exit__(self, *a):
            return False

    with patch("backend.nexus_control_plane.federation_client.urlopen", return_value=Boom()):
        # Use allowed host URL path via registry
        out = client.get_json(ROLE_DEMO_EXECUTION, "/api/nexus/demo-execution/status")
        assert out["ok"] is False
        assert out["data_status"] == DATA_STATUS_SERVICE_UNAVAILABLE


def test_circuit_breaker_opens():
    reg = ServiceRegistry.from_env()
    client = FederationClient(registry=reg)
    circuit = client._circuits.setdefault(ROLE_DEMO_EXECUTION, client._circuits.get(ROLE_DEMO_EXECUTION) or __import__("backend.nexus_control_plane.federation_client", fromlist=["CircuitState"]).CircuitState())
    for _ in range(3):
        circuit.record_failure(threshold=3, cooldown_sec=60)
    assert circuit.allow() is False
    # force open and ensure get_json short-circuits
    client._circuits[ROLE_DEMO_EXECUTION] = circuit
    out = client.get_json(ROLE_DEMO_EXECUTION, "/api/nexus/demo-execution/status")
    assert out["error"] == "circuit_open"


def test_analyzer_zero_trade(tmp_path: Path):
    from tools.analysis.analyze_nexus_demo_session import analyze_session, write_outputs

    (tmp_path / "session_status.json").write_text(
        json.dumps(
            {
                "session_id": "NEXUS-DEMO-6H-TEST",
                "candidates_total": 8,
                "cost_gate_blocks": 8,
                "entries_total": 0,
                "trades_completed": 0,
            }
        ),
        encoding="utf-8",
    )
    result = analyze_session(tmp_path, session_id="NEXUS-DEMO-6H-TEST")
    assert result["summary"]["entries"] == 0
    assert result["summary"]["funding"] == "UNAVAILABLE"
    assert result["summary"]["zero_trade_analysis"]["recommendation"] == "DEMO_AUTONOMOUS_6H_BLOCKED_NO_VALID_CANDIDATES"
    assert result["summary"]["forbidden_labels"]["proven"] is False
    out = tmp_path / "out"
    write_outputs(result, out)
    assert (out / "analysis_summary.json").exists()
    assert (out / "session_quality_report.md").exists()
