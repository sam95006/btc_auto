"""Additional Founder fee + geometry + single-service policy tests."""
from __future__ import annotations

import os
from datetime import date

import pytest

from backend.nexus_demo_execution.fee_rate import (
    FEE_RATE_CONFIG_EXPIRED,
    FEE_RATE_CONFIGURED_CONSERVATIVE,
    clear_fee_cache,
    config_is_expired,
    configured_conservative_quote,
    fee_policy_public_status,
)
from backend.nexus_demo_execution.market_structure import (
    atr_from_ohlc,
    build_geometry_inputs_from_klines,
)
from backend.nexus_demo_execution.trade_geometry import compute_structure_geometry


@pytest.fixture(autouse=True)
def _env_cleanup():
    clear_fee_cache()
    keys = [k for k in os.environ if k.startswith("NEXUS_FEE_RATE")]
    saved = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    yield
    for k in keys:
        os.environ.pop(k, None)
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
    clear_fee_cache()


def _enable_founder_fee():
    os.environ["NEXUS_FEE_RATE_CONSERVATIVE_ENABLED"] = "true"
    os.environ["NEXUS_FEE_RATE_CONSERVATIVE_FOUNDER_APPROVED"] = "true"
    os.environ["NEXUS_FEE_RATE_CONSERVATIVE_TAKER"] = "0.00055"
    os.environ["NEXUS_FEE_RATE_CONSERVATIVE_MAKER"] = "0.00020"
    os.environ["NEXUS_FEE_RATE_VERSION"] = "founder-conservative-v1-2026-07-31"
    os.environ["NEXUS_FEE_RATE_SOURCE"] = "BYBIT_PUBLIC_VIP0_BASE_SCHEDULE"
    os.environ["NEXUS_FEE_RATE_REVIEW_BY"] = "2026-08-31"


def test_configured_fee_requires_founder_approval():
    os.environ["NEXUS_FEE_RATE_CONSERVATIVE_ENABLED"] = "true"
    os.environ["NEXUS_FEE_RATE_CONSERVATIVE_TAKER"] = "0.00055"
    assert configured_conservative_quote("BTCUSDT") is None


def test_configured_fee_pretrade_uses_taker_both_sides():
    _enable_founder_fee()
    q = configured_conservative_quote("BTCUSDT")
    assert q is not None
    assert q.status == FEE_RATE_CONFIGURED_CONSERVATIVE
    assert q.fee_source == "FOUNDER_APPROVED_CONFIG"
    assert q.fee_account_specific is False
    assert q.fee_live_private_api is False
    assert q.fee_endpoint_supported is False
    assert q.pretrade_entry_fee_rate == pytest.approx(0.00055)
    assert q.pretrade_exit_fee_rate == pytest.approx(0.00055)
    assert q.pretrade_round_trip_fee_rate == pytest.approx(0.00110)
    assert q.maker_fee_rate == pytest.approx(0.00020)


def test_configured_fee_expiry_blocks_entry():
    _enable_founder_fee()
    os.environ["NEXUS_FEE_RATE_REVIEW_BY"] = "2026-07-01"
    assert config_is_expired(today=date(2026, 7, 31)) is True
    q = configured_conservative_quote("ETHUSDT")
    assert q is not None
    assert q.status == FEE_RATE_CONFIG_EXPIRED
    assert q.new_entry_blocked is True
    assert q.usable_taker is None


def test_fee_policy_public_status_never_claims_live():
    _enable_founder_fee()
    st = fee_policy_public_status()
    assert st["fee_rate_status"] == FEE_RATE_CONFIGURED_CONSERVATIVE
    assert st["fee_live_private_api"] is False
    assert st["fee_account_specific"] is False
    assert "LIVE" not in st["fee_rate_status"]


def test_atr_and_structure_geometry_long():
    candles = []
    price = 100.0
    for i in range(40):
        candles.append(
            {
                "open": price,
                "high": price + 1.5,
                "low": price - 1.2,
                "close": price + 0.3,
                "volume": 1000,
            }
        )
        price += 0.2
    atr = atr_from_ohlc(candles, 14)
    assert atr is not None and atr > 0
    geom = build_geometry_inputs_from_klines(last_price=price, klines=candles)
    assert geom["geometry_status"] == "GEOMETRY_INPUTS_COMPLETE"
    g = compute_structure_geometry(
        side="Buy",
        entry_price=price,
        atr=float(geom["atr"]),
        recent_swing_high=float(geom["recent_swing_high"]),
        recent_swing_low=float(geom["recent_swing_low"]),
        support=float(geom["support"]),
        resistance=float(geom["resistance"]),
        fee_rate=0.00055,
        spread_bps=1.0,
        slippage_bps=1.0,
        funding_rate=0.0001,
        qty=5.0,
        tick_size=0.01,
    )
    assert g.block_reason != "GEOMETRY_INPUT_MISSING"
