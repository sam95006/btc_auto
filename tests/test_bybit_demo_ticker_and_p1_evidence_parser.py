from __future__ import annotations

import json
import io
import sys

from backend.nexus_demo_execution.demo_write_client import DemoWriteClient
from tools.ci import p1_parse_exec_json
from tools.ci.p1_parse_exec_json import _load


def test_fetch_ticker_preserves_official_bybit_v5_envelope_time(monkeypatch) -> None:
    client = DemoWriteClient(api_key="demo-key", api_secret="demo-secret")
    response = {
        "retCode": 0,
        "result": {
            "category": "linear",
            "list": [{"symbol": "ETHUSDT", "lastPrice": "2450.50"}],
        },
        "retExtInfo": {},
        "time": 1234567890000,
    }
    monkeypatch.setattr(client, "public_get", lambda *_args, **_kwargs: response)

    ticker = client.fetch_ticker("ETHUSDT")

    assert ticker["time"] == 1234567890000
    assert ticker["lastPrice"] == "2450.50"


def test_fetch_ticker_does_not_synthesize_missing_envelope_time(monkeypatch) -> None:
    client = DemoWriteClient(api_key="demo-key", api_secret="demo-secret")
    monkeypatch.setattr(
        client,
        "public_get",
        lambda *_args, **_kwargs: {"retCode": 0, "result": {"list": [{"symbol": "ETHUSDT", "lastPrice": "2450.50"}]}},
    )

    assert "time" not in client.fetch_ticker("ETHUSDT")


def test_pretty_nested_p1_evidence_document_loads() -> None:
    payload = {
        "BYBIT_DEMO_SINGLE_TRADE_E2E_PASS": "HOLD",
        "P1_PREFLIGHT_PASS": False,
        "FRESH_OFFICIAL_EXECUTION_DATA_PASS": False,
        "NO_MOCK_EXECUTION_PRICE_PASS": False,
        "RISK_ENGINE_FINAL_AUTHORITY_PASS": False,
        "create_order_calls": 0,
        "error": "ETHUSDT:ticker_time_missing",
        "preflight": {"symbol": "ETHUSDT", "market": {"age_ms": None}},
        "startup_reconcile": {"clear": True},
        "migrations": {"0005": True, "0006": True},
        "process_flags": {"MAINNET": False, "EXCHANGE_WRITE": False},
    }

    assert _load(json.dumps(payload, indent=2)) == payload


def test_pretty_nested_p1_pass_evidence_document_loads() -> None:
    payload = {
        "BYBIT_DEMO_SINGLE_TRADE_E2E_PASS": "PASS",
        "preflight": {"official": {"time": 1234567890000}},
        "startup_reconcile": {"clear": True},
        "migrations": {"0005": True, "0006": True},
        "process_flags": {"MAINNET": False, "EXCHANGE_WRITE": False},
    }

    assert _load(json.dumps(payload, indent=2))["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "PASS"


def test_pretty_hold_evidence_returns_normal_hold_exit(monkeypatch, tmp_path) -> None:
    payload = {
        "BYBIT_DEMO_SINGLE_TRADE_E2E_PASS": "HOLD",
        "P1_PREFLIGHT_PASS": False,
        "FRESH_OFFICIAL_EXECUTION_DATA_PASS": False,
        "NO_MOCK_EXECUTION_PRICE_PASS": False,
        "RISK_ENGINE_FINAL_AUTHORITY_PASS": False,
        "create_order_calls": 0,
        "error": "ETHUSDT:ticker_time_missing",
        "preflight": {"nested": {"state": "HOLD"}},
    }
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload, indent=2)))

    assert p1_parse_exec_json.main() == 1
    assert (tmp_path / "artifacts/bybit_demo_p1/p1_qualification_evidence.json").is_file()
