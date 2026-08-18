from __future__ import annotations

import json
import io
import sys
from pathlib import Path

import pytest

from backend.nexus_demo_execution.demo_write_client import (
    DemoWriteClient,
    DemoWriteError,
    official_server_time_ms,
)
from tools.ci import p1_parse_exec_json
from tools.ci.p1_parse_exec_json import _load


ROOT = Path(__file__).resolve().parents[1]


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


def test_fetch_server_time_uses_only_official_bybit_response_fields(monkeypatch) -> None:
    client = DemoWriteClient(api_key="demo-key", api_secret="demo-secret")
    monkeypatch.setattr(
        client,
        "public_get",
        lambda *_args, **_kwargs: {"retCode": 0, "result": {"timeSecond": "1234567890"}},
    )

    assert client.fetch_server_time() == 1234567890000


def test_official_server_time_prefers_time_nano() -> None:
    payload = {
        "retCode": 0,
        "time": 1_234_567_890_000,
        "result": {"timeSecond": "1234567890", "timeNano": "1234567890123456789"},
    }
    assert official_server_time_ms(payload) == 1_234_567_890_123


def test_official_server_time_uses_top_level_time_when_nano_missing() -> None:
    payload = {"retCode": 0, "time": 1_234_567_890_000, "result": {"timeSecond": "1234567890"}}
    assert official_server_time_ms(payload) == 1_234_567_890_000


def test_fetch_server_time_prefers_official_time_nano(monkeypatch) -> None:
    client = DemoWriteClient(api_key="demo-key", api_secret="demo-secret")
    monkeypatch.setattr(
        client,
        "public_get",
        lambda *_args, **_kwargs: {
            "retCode": 0,
            "time": 1_234_567_890_000,
            "result": {"timeSecond": "1234567890", "timeNano": "1234567890123456789"},
        },
    )
    assert client.fetch_server_time() == 1_234_567_890_123


def test_fetch_server_time_missing_official_fields_does_not_use_local_clock(monkeypatch) -> None:
    client = DemoWriteClient(api_key="demo-key", api_secret="demo-secret")
    monkeypatch.setattr(client, "public_get", lambda *_args, **_kwargs: {"retCode": 0, "result": {}})
    with pytest.raises(DemoWriteError) as exc:
        client.fetch_server_time()
    assert exc.value.code == "server_time_missing"


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


def test_qualification_workflow_requires_read_only_runtime_identity_and_shape_probes() -> None:
    source = (ROOT / ".github/workflows/founder_approved_bybit_demo_p1_qualification.yml").read_text(encoding="utf-8")
    assert "P1_RUNTIME_TICKER_FIX_PRESENT=true" in source
    assert "P1_RUNTIME_CODE_IDENTITY_PASS=true" in source
    assert "inspect.getsource(DemoWriteClient.fetch_ticker)" in source
    assert "ticker_top_level_time_present" in source
    assert "ticker_last_price_present" in source
    assert source.index("P1_RUNTIME_CODE_IDENTITY_PASS=true") < source.index(
        "python -m backend.nexus_demo_execution.p1_qualification"
    )
