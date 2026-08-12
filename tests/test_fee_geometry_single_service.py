"""Tests for fee capability honesty and structure geometry gates."""
from __future__ import annotations

import os

import pytest

from backend.nexus_demo_execution.cost_entry_gate import evaluate_cost_gate
from backend.nexus_demo_execution.fee_rate import (
    DEMO_FEE_ENDPOINT_UNSUPPORTED,
    FEE_RATE_AUTH_FAILED,
    FEE_RATE_CONFIGURED_CONSERVATIVE,
    FEE_RATE_LIVE,
    FEE_RATE_UNAVAILABLE,
    classify_demo_fee_error,
    clear_fee_cache,
    configured_conservative_quote,
    parse_fee_rows,
)
from backend.nexus_demo_execution.trade_geometry import (
    compute_structure_geometry,
    evaluate_fixed_symmetric_percent,
)
from tools.analysis.probe_bybit_demo_fee_rate_capability import _classify


@pytest.fixture(autouse=True)
def _clear():
    clear_fee_cache()
    for k in list(os.environ):
        if k.startswith("NEXUS_FEE_RATE_CONSERVATIVE"):
            os.environ.pop(k, None)
    yield
    clear_fee_cache()


def test_demo_fee_endpoint_supported_live():
    q = parse_fee_rows([{"makerFeeRate": "0.0002", "takerFeeRate": "0.00055"}], "BTCUSDT")
    assert q.status == FEE_RATE_LIVE


def test_demo_fee_endpoint_unsupported_classification():
    c = _classify(200, 10001, "demo trading does not support this endpoint", [])
    assert c["fee_rate_status"] == "DEMO_FEE_ENDPOINT_UNSUPPORTED"
    assert c["endpoint_supported"] is False


def test_fee_auth_failed_not_confused_with_unsupported():
    assert classify_demo_fee_error("credentials_missing", "") == FEE_RATE_AUTH_FAILED
    assert classify_demo_fee_error("api_error", "10003:invalid") == FEE_RATE_AUTH_FAILED
    assert classify_demo_fee_error("api_error", "not supported on demo") == DEMO_FEE_ENDPOINT_UNSUPPORTED


def test_fee_schema_mismatch():
    q = parse_fee_rows([{"makerFeeRate": "x", "takerFeeRate": "y"}], "ETHUSDT")
    assert q.status != FEE_RATE_LIVE
    assert q.usable_taker is None


def test_configured_conservative_requires_founder_approval():
    os.environ["NEXUS_FEE_RATE_CONSERVATIVE_ENABLED"] = "true"
    os.environ["NEXUS_FEE_RATE_CONSERVATIVE_TAKER"] = "0.00055"
    assert configured_conservative_quote("BTCUSDT") is None
    os.environ["NEXUS_FEE_RATE_CONSERVATIVE_FOUNDER_APPROVED"] = "true"
    q = configured_conservative_quote("BTCUSDT")
    assert q is not None
    assert q.status == FEE_RATE_CONFIGURED_CONSERVATIVE
    assert q.fee_source == "FOUNDER_APPROVED_CONFIG"


def test_unavailable_never_becomes_zero():
    r = evaluate_cost_gate(
        entry_price=100,
        stop_loss=99,
        take_profit=101,
        qty=5,
        side="Buy",
        fee_rate=None,
        funding_rate=None,
        slippage_bps=1,
        fee_meta={"status": FEE_RATE_UNAVAILABLE},
    )
    assert r.estimated_total_cost == "UNAVAILABLE"
    assert r.estimated_net_reward == "UNAVAILABLE"


def test_symmetric_geometry_fails_net_rr():
    g = evaluate_fixed_symmetric_percent(
        side="Buy",
        entry_price=100,
        tp_pct=0.008,
        sl_pct=0.008,
        fee_rate=0.00055,
        spread_bps=1,
        slippage_bps=1,
        funding_rate=0.0001,
        qty=5,
    )
    assert g.gross_rr == pytest.approx(1.0)
    assert g.net_rr < 1.2
    assert g.allowed is False
    assert "FIXED_SYMMETRIC_GEOMETRY_INCOMPATIBLE_WITH_NET_RR_GATE" in g.labels


def test_structure_geometry_valid_long():
    g = compute_structure_geometry(
        side="Buy",
        entry_price=100,
        atr=2.0,
        recent_swing_high=108,
        recent_swing_low=97,
        support=96,
        resistance=110,
        spread_bps=1,
        slippage_bps=1,
        fee_rate=0.00055,
        funding_rate=0.0001,
        tick_size=0.01,
        qty=5,
    )
    assert g.block_reason != "GEOMETRY_INPUT_MISSING"
    assert isinstance(g.net_rr, float)


def test_structure_geometry_missing_input():
    g = compute_structure_geometry(
        side="Sell",
        entry_price=100,
        fee_rate=0.00055,
        qty=5,
    )
    assert g.block_reason == "GEOMETRY_INPUT_MISSING"
    assert "atr" in g.inputs_missing


def test_no_future_data_in_structure_module_defaults():
    # compute_structure_geometry must not invent swings when absent
    g = compute_structure_geometry(side="Buy", entry_price=100, fee_rate=0.00055, qty=1)
    assert g.inputs_missing
    assert g.stop_loss == "UNAVAILABLE"


def test_single_service_registry_flags():
    os.environ["NEXUS_SINGLE_SERVICE"] = "true"
    os.environ["NEXUS_SELF_URL"] = "http://127.0.0.1:8080"
    from backend.nexus_control_plane.service_registry import ServiceRegistry

    reg = ServiceRegistry.from_env()
    urls = {r.service_url for r in reg.records.values()}
    assert urls == {"http://127.0.0.1:8080"}
    assert sum(1 for r in reg.records.values() if r.execution_owner) == 1
    os.environ.pop("NEXUS_SINGLE_SERVICE", None)
