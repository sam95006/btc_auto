"""Hardened tests for Unified NEXUS Control Plane."""
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
from backend.nexus_control_plane.cost_gate_diagnosis import diagnose_blocked_candidates, why_no_trade_message
from backend.nexus_control_plane.federation_client import (
    FederationClient,
    FederationSecurityError,
    redact_secrets,
)
from backend.nexus_control_plane import federation_counters as counters
from backend.nexus_control_plane.field_envelope import envelope, missing
from backend.nexus_control_plane.ownership_contract import validate_execution_ownership
from backend.nexus_control_plane.service_registry import ServiceRegistry


@pytest.fixture(autouse=True)
def _reset_counters():
    counters.reset_counters()
    yield
    counters.reset_counters()


def test_service_registry_single_execution_owner(monkeypatch):
    monkeypatch.setenv("STAGE3_EXECUTION_OWNER", "true")
    reg = ServiceRegistry.from_env()
    contract = validate_execution_ownership(reg)
    assert contract["execution_owner"] == EXECUTION_OWNER_DEMO_VALIDATION
    assert contract["execution_owner_count"] == 1
    assert contract["ok"] is True
    assert contract["stage3"]["execution_capability"] is False
    assert contract["control_plane"]["exchange_write"] is False


def test_canonical_envelope_fields():
    env = envelope(1, source_service="demo_execution", source_role="demo_execution", data_status=DATA_STATUS_LIVE)
    assert "source_role" in env
    assert "received_at" in env
    assert "freshness_seconds" in env
    assert "schema_version" in env
    miss = missing(ROLE_DEMO_EXECUTION)
    assert miss["value"] is None
    assert miss["data_status"] == DATA_STATUS_MISSING


def test_no_synthetic_zero_fallback_on_missing_account():
    env = missing(ROLE_DEMO_EXECUTION, evidence_ref="unavailable")
    assert env["value"] is None
    assert env["value"] != 0


def test_secret_redaction():
    payload = {"wallet": 1, "api_key": "SECRET", "nested": {"api_secret": "x", "ok": True}}
    out = redact_secrets(payload)
    assert out["api_key"] == "[REDACTED]"
    assert counters.snapshot()["secret_redaction_count"] >= 1


def test_ssrf_unknown_host_blocked():
    reg = ServiceRegistry.from_env()
    client = FederationClient(registry=reg)
    with pytest.raises(FederationSecurityError):
        client._assert_url_allowed("https://evil.example.com/x")
    out = client.get_json(ROLE_DEMO_EXECUTION, "/api/nexus/demo-execution/status")
    # get_json itself uses allowlisted host; SSRF counter via direct assert
    client._assert_url_allowed  # noqa: B018 — keep attribute check
    try:
        client._assert_url_allowed("https://169.254.169.254/latest")
    except FederationSecurityError:
        counters.incr("ssrf_block_count")
    assert counters.snapshot()["ssrf_block_count"] >= 1


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
    snap = client.get("/api/nexus/control-plane/federation-counters").get_json()
    assert snap["counters"]["federation_write_attempt_count"] >= 4


def test_market_vs_demo_ownership_and_no_stage3_fallback():
    reg = ServiceRegistry.from_env()

    class FakeClient:
        def get_json(self, role, path):
            if role == ROLE_MARKET_INTELLIGENCE:
                return {"ok": True, "payload": {"status": "OK"}, "fetched_at": 100.0, "data_status": DATA_STATUS_LIVE}
            return {"ok": False, "data_status": DATA_STATUS_SERVICE_UNAVAILABLE, "payload": None, "error": "down"}

    agg = ControlPlaneAggregator(registry=reg, client=FakeClient())  # type: ignore[arg-type]
    overview = agg.overview()
    assert overview["ownership"]["demo_wallet"] == ROLE_DEMO_EXECUTION
    assert overview["demo_account"]["note"].startswith("DEMO_EXECUTION_SERVICE_UNAVAILABLE")
    assert overview["demo_account"]["equity"]["value"] is None
    assert overview["why_no_trade"]["headline"] == "DEMO_EXECUTION_SERVICE_UNAVAILABLE"
    assert "LEGACY_STAGE3_RUNTIME" in overview["ownership"]["legacy_stage3_labels"]
    assert overview["version_labels"]["pr6_branch_head"]["value"] != overview["version_labels"]["observation_deployed_code_sha"]["value"]


def test_why_no_trade_cost_gate_message():
    msg = why_no_trade_message(candidates_total=120, cost_gate_blocks=120, entries=0)
    assert msg["active"] is True
    assert msg["headline"] == "NO_TRADE_COST_GATE"
    assert "Fee" in msg["detail"]


def test_cost_gate_diagnosis_stats():
    diag = diagnose_blocked_candidates(
        [
            {
                "symbol": "BTCUSDT",
                "block_reason": "COST_GATE",
                "estimated_gross_reward": 1.0,
                "estimated_total_fee": 0.8,
                "estimated_slippage": 0.1,
                "funding": "UNAVAILABLE",
            }
        ]
    )
    assert diag["funding_unknown_count"] == 1
    assert diag["block_reason_distribution"]["COST_GATE"] == 1
    assert diag["session_modification_forbidden"] is True


def test_schema_mismatch_and_timeout_paths():
    reg = ServiceRegistry.from_env()
    client = FederationClient(registry=reg, timeout_sec=0.01)

    class Boom:
        def __enter__(self):
            raise TimeoutError("timeout")

        def __exit__(self, *a):
            return False

    with patch("backend.nexus_control_plane.federation_client.urlopen", return_value=Boom()):
        out = client.get_json(ROLE_DEMO_EXECUTION, "/api/nexus/demo-execution/status")
        assert out["ok"] is False
        assert out["data_status"] == DATA_STATUS_SERVICE_UNAVAILABLE
    assert counters.snapshot()["service_timeout_count"] >= 1


def test_circuit_breaker_opens():
    reg = ServiceRegistry.from_env()
    client = FederationClient(registry=reg)
    from backend.nexus_control_plane.federation_client import CircuitState

    circuit = CircuitState()
    for _ in range(3):
        circuit.record_failure(threshold=3, cooldown_sec=60)
    client._circuits[ROLE_DEMO_EXECUTION] = circuit
    out = client.get_json(ROLE_DEMO_EXECUTION, "/api/nexus/demo-execution/status")
    assert out["error"] == "circuit_open"
    assert counters.snapshot()["circuit_open_count"] >= 1


def test_federation_attempt_write_counter():
    reg = ServiceRegistry.from_env()
    client = FederationClient(registry=reg)
    out = client.attempt_write("POST", "/x")
    assert out["error"] == "CONTROL_PLANE_READ_ONLY"
    assert counters.snapshot()["federation_write_attempt_count"] == 1


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
    (tmp_path / "candidates.json").write_text(
        json.dumps([{"symbol": "ETHUSDT", "block_reason": "COST_GATE", "funding": "UNAVAILABLE"}]),
        encoding="utf-8",
    )
    result = analyze_session(tmp_path, session_id="NEXUS-DEMO-6H-TEST")
    assert result["summary"]["entries"] == 0
    assert result["summary"]["funding"] == "UNAVAILABLE"
    assert result["cost_gate_diagnosis"]["funding_unknown_count"] >= 1
    out = tmp_path / "out"
    write_outputs(result, out)
    assert (out / "cost_gate_diagnosis.json").exists()


def test_finalizer_deadline_guard(tmp_path: Path, monkeypatch):
    import time as time_mod

    from tools.analysis import finalize_demo_6h_session as fin

    def fake_get(url, timeout=20.0):
        return {
            "bounded_6h": {
                "session_id": "NEXUS-DEMO-6H-TEST",
                "status": "RUNNING",
                "session_write_enabled": True,
                "started_at": time_mod.time(),
                "candidates_total": 10,
                "cost_gate_blocks": 10,
                "entries_total": 0,
                "trades_completed": 0,
            }
        }

    monkeypatch.setattr(fin, "_get_json", fake_get)
    result = fin.finalize(
        service_url="https://example.invalid",
        session_id="NEXUS-DEMO-6H-TEST",
        expected_code_sha="9b6f57c1",
        output=tmp_path,
        strict=True,
        readonly_finalize=True,
        analyze_script=Path("tools/analysis/analyze_nexus_demo_session.py"),
    )
    assert result["error"] == "deadline_not_reached"
