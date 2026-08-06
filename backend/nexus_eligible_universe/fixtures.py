"""Deterministic public-catalog fixtures for V18-C Eligible Universe.

Counts are derived by running the engine over these rows — never hardcoded
funnel fakes. Each row models a realistic linear USDT perpetual profile.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_eligible_universe.models import InstrumentSnapshot

# Fixed evaluation clock (2026-08-06T00:00:00Z)
AS_OF_MS = 1_754_438_400_000
# 30 days before as_of
LAUNCH_OLD_MS = AS_OF_MS - 30 * 86_400_000
# 2 days before as_of (new listing)
LAUNCH_NEW_MS = AS_OF_MS - 2 * 86_400_000


def _healthy(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "symbol": "BTCUSDT",
        "exchange": "bybit",
        "category": "linear",
        "status": "Trading",
        "quote_coin": "USDT",
        "base_coin": "BTC",
        "launch_time_ms": LAUNCH_OLD_MS,
        "tick_size": 0.1,
        "lot_size": 0.001,
        "min_notional": 5.0,
        "contract_type": "LinearPerpetual",
        "turnover_24h": 2_500_000_000.0,
        "trade_count_24h": 1_200_000,
        "spread_bps": 1.2,
        "book_depth_usdt": 8_000_000.0,
        "funding_rate": 0.0001,
        "funding_available": True,
        "open_interest_value": 4_000_000_000.0,
        "oi_available": True,
        "history_bars": 5000,
        "data_completeness": 0.98,
        "data_trust_status": "TRUSTED",
        "license_status": "APPROVED_PUBLIC",
        "delisting_flag": False,
        "round_trip_cost_bps": 8.0,
        "last_price": 65000.0,
    }
    base.update(overrides)
    return base


def fixture_catalog_raw() -> list[dict[str, Any]]:
    """Diverse catalog covering every universe class + funnel stages."""
    return [
        # --- ELIGIBLE cluster ---
        _healthy(symbol="BTCUSDT"),
        _healthy(
            symbol="ETHUSDT",
            base_coin="ETH",
            tick_size=0.01,
            lot_size=0.01,
            last_price=3200.0,
            turnover_24h=1_100_000_000.0,
            open_interest_value=1_500_000_000.0,
            spread_bps=1.5,
        ),
        _healthy(
            symbol="SOLUSDT",
            base_coin="SOL",
            tick_size=0.001,
            lot_size=0.1,
            last_price=150.0,
            turnover_24h=420_000_000.0,
            open_interest_value=380_000_000.0,
            spread_bps=2.0,
            trade_count_24h=450_000,
        ),
        # --- OBSERVE_ONLY: funding missing (known false) ---
        _healthy(
            symbol="OBS_NO_FUND",
            base_coin="OBS",
            funding_available=False,
            funding_rate=None,
        ),
        # --- OBSERVE_ONLY: OI too low but otherwise liquid ---
        _healthy(
            symbol="OBS_LOW_OI",
            base_coin="OBL",
            open_interest_value=50_000.0,
            oi_available=True,
        ),
        # --- OBSERVE_ONLY: USABLE_WITH_LIMITS trust ---
        _healthy(
            symbol="OBS_TRUST_LIMITS",
            base_coin="OTL",
            data_trust_status="USABLE_WITH_LIMITS",
            data_completeness=0.85,
        ),
        # --- LOW_LIQUIDITY ---
        _healthy(
            symbol="THINUSDT",
            base_coin="THIN",
            turnover_24h=100_000.0,
            trade_count_24h=200,
            book_depth_usdt=1_000.0,
            open_interest_value=80_000.0,
        ),
        # --- WIDE_SPREAD ---
        _healthy(
            symbol="WIDEUSDT",
            base_coin="WIDE",
            spread_bps=80.0,
            round_trip_cost_bps=20.0,
        ),
        # --- INSUFFICIENT_HISTORY ---
        _healthy(
            symbol="SHORTUSDT",
            base_coin="SHORT",
            history_bars=12,
        ),
        # --- NEW_LISTING ---
        _healthy(
            symbol="NEWUSDT",
            base_coin="NEW",
            launch_time_ms=LAUNCH_NEW_MS,
            history_bars=40,
        ),
        # --- DELISTING_RISK ---
        _healthy(
            symbol="BYEUSDT",
            base_coin="BYE",
            status="PreDelisting",
            delisting_flag=True,
        ),
        # --- DATA_DEGRADED (trust) ---
        _healthy(
            symbol="DEGUSDT",
            base_coin="DEG",
            data_trust_status="DEGRADED",
            data_completeness=0.82,
        ),
        # --- DATA_DEGRADED (completeness) ---
        _healthy(
            symbol="GAPUSDT",
            base_coin="GAP",
            data_completeness=0.40,
        ),
        # --- COST_INFEASIBLE ---
        _healthy(
            symbol="COSTUSDT",
            base_coin="COST",
            spread_bps=10.0,
            round_trip_cost_bps=95.0,
        ),
        # --- MARKET_HALTED ---
        _healthy(
            symbol="HALTUSDT",
            base_coin="HALT",
            status="Halt",
        ),
        # --- LICENSE_BLOCKED ---
        _healthy(
            symbol="LICUSDT",
            base_coin="LIC",
            data_trust_status="LICENSE_BLOCKED",
            license_status="LICENSE_REVIEW_REQUIRED",
        ),
        # --- UNAVAILABLE: missing turnover (must NOT become ELIGIBLE) ---
        _healthy(
            symbol="UNK_TURN",
            base_coin="UNK",
            turnover_24h=None,
        ),
        # --- UNAVAILABLE: unknown trust ---
        _healthy(
            symbol="UNK_TRUST",
            base_coin="UKT",
            data_trust_status=None,
        ),
        # --- UNAVAILABLE: missing contract specs ---
        _healthy(
            symbol="BADSPEC",
            base_coin="BAD",
            tick_size=None,
            lot_size=None,
            min_notional=None,
        ),
        # --- UNAVAILABLE: trust UNAVAILABLE ---
        _healthy(
            symbol="NAUSDT",
            base_coin="NA",
            data_trust_status="UNAVAILABLE",
            data_completeness=0.05,
        ),
        # Extra healthy names to enrich funnel (still computed, not hardcoded)
        _healthy(
            symbol="XRPUSDT",
            base_coin="XRP",
            tick_size=0.0001,
            lot_size=1.0,
            last_price=0.55,
            turnover_24h=180_000_000.0,
            open_interest_value=220_000_000.0,
            trade_count_24h=300_000,
            spread_bps=2.5,
        ),
        _healthy(
            symbol="DOGEUSDT",
            base_coin="DOGE",
            tick_size=0.00001,
            lot_size=10.0,
            last_price=0.12,
            turnover_24h=95_000_000.0,
            open_interest_value=110_000_000.0,
            trade_count_24h=280_000,
            spread_bps=3.0,
        ),
        _healthy(
            symbol="PEPEUSDT",
            base_coin="PEPE",
            tick_size=0.0000001,
            lot_size=100_000.0,
            last_price=0.00001,
            turnover_24h=75_000_000.0,
            open_interest_value=90_000_000.0,
            trade_count_24h=210_000,
            spread_bps=4.0,
            book_depth_usdt=400_000.0,
        ),
        # Catalog-invalid quote
        _healthy(
            symbol="BTCUSD",
            base_coin="BTC",
            quote_coin="USD",
            contract_type="InversePerpetual",
        ),
    ]


def fixture_instruments() -> list[InstrumentSnapshot]:
    out: list[InstrumentSnapshot] = []
    for row in fixture_catalog_raw():
        payload = deepcopy(row)
        out.append(InstrumentSnapshot(**payload))
    return out


def expected_class_for_symbol(symbol: str) -> str | None:
    """Sparse expectations for adversarial / regression checks."""
    mapping = {
        "BTCUSDT": "ELIGIBLE",
        "ETHUSDT": "ELIGIBLE",
        "SOLUSDT": "ELIGIBLE",
        "XRPUSDT": "ELIGIBLE",
        "DOGEUSDT": "ELIGIBLE",
        "PEPEUSDT": "ELIGIBLE",
        "OBS_NO_FUND": "OBSERVE_ONLY",
        "OBS_LOW_OI": "OBSERVE_ONLY",
        "OBS_TRUST_LIMITS": "OBSERVE_ONLY",
        "THINUSDT": "LOW_LIQUIDITY",
        "WIDEUSDT": "WIDE_SPREAD",
        "SHORTUSDT": "INSUFFICIENT_HISTORY",
        "NEWUSDT": "NEW_LISTING",
        "BYEUSDT": "DELISTING_RISK",
        "DEGUSDT": "DATA_DEGRADED",
        "GAPUSDT": "DATA_DEGRADED",
        "COSTUSDT": "COST_INFEASIBLE",
        "HALTUSDT": "MARKET_HALTED",
        "LICUSDT": "LICENSE_BLOCKED",
        "UNK_TURN": "UNAVAILABLE",
        "UNK_TRUST": "UNAVAILABLE",
        "BADSPEC": "UNAVAILABLE",
        "NAUSDT": "UNAVAILABLE",
        "BTCUSD": "UNAVAILABLE",
    }
    return mapping.get(symbol)
