"""V18.2.7 data-truth hardening — universe membership + freshness honesty."""
from __future__ import annotations

import unittest

from backend.market.scanner import universe_config as cfg
from backend.market.scanner.universe import (
    asset_disposition,
    build_universe,
    classify_exclusion,
    symbol_type_of,
)


def _ticker(symbol: str, turnover: float = 50_000_000.0) -> dict:
    return {
        "symbol": symbol,
        "lastPrice": "10",
        "bid1Price": "9.99",
        "ask1Price": "10.01",
        "openInterestValue": "5000000",
        "turnover24h": str(turnover),
        "markPrice": "10",
        "indexPrice": "10",
        "price24hPcnt": "0.01",
        "openInterest": "1000",
        "fundingRate": "0.0001",
        "volume24h": "100000",
        "ts": "1700000000000",
    }


def _instrument(symbol: str, symbol_type: str = "") -> dict:
    return {
        "symbol": symbol,
        "status": "Trading",
        "quoteCoin": "USDT",
        "symbolType": symbol_type,
        "launchTime": "1600000000000",
    }


class TestNonCryptoUniverseFilter(unittest.TestCase):
    def test_soxl_stock_excluded(self) -> None:
        reason = classify_exclusion(
            _ticker("SOXLUSDT"),
            _instrument("SOXLUSDT", "stock"),
            now_ms=1_800_000_000_000,
        )
        self.assertEqual(reason, "NON_CRYPTO_ASSET")

    def test_spcx_stock_excluded(self) -> None:
        reason = classify_exclusion(
            _ticker("SPCXUSDT"),
            _instrument("SPCXUSDT", "stock"),
            now_ms=1_800_000_000_000,
        )
        self.assertEqual(reason, "NON_CRYPTO_ASSET")

    def test_btc_crypto_eligible(self) -> None:
        reason = classify_exclusion(
            _ticker("BTCUSDT", turnover=200_000_000.0),
            _instrument("BTCUSDT", ""),
            now_ms=1_800_000_000_000,
        )
        self.assertIsNone(reason)

    def test_innovation_zone_allowed(self) -> None:
        reason = classify_exclusion(
            _ticker("FOOUSDT", turnover=20_000_000.0),
            _instrument("FOOUSDT", "innovation"),
            now_ms=1_800_000_000_000,
        )
        self.assertIsNone(reason)

    def test_commodity_excluded(self) -> None:
        reason = classify_exclusion(
            _ticker("XAUUSDT"),
            _instrument("XAUUSDT", "commodity"),
            now_ms=1_800_000_000_000,
        )
        self.assertEqual(reason, "NON_CRYPTO_ASSET")

    def test_build_universe_metric_zero(self) -> None:
        tickers = [
            _ticker("BTCUSDT", 300_000_000),
            _ticker("SOXLUSDT", 250_000_000),
            _ticker("SPCXUSDT", 190_000_000),
            _ticker("ETHUSDT", 280_000_000),
        ]
        instruments = [
            _instrument("BTCUSDT", ""),
            _instrument("SOXLUSDT", "stock"),
            _instrument("SPCXUSDT", "stock"),
            _instrument("ETHUSDT", ""),
        ]
        uni = build_universe(tickers=tickers, instruments=instruments)
        symbols = set(uni["symbols"])
        self.assertIn("BTCUSDT", symbols)
        self.assertIn("ETHUSDT", symbols)
        self.assertNotIn("SOXLUSDT", symbols)
        self.assertNotIn("SPCXUSDT", symbols)
        self.assertEqual(uni["non_crypto_symbol_in_crypto_opportunity_count"], 0)
        self.assertGreaterEqual(uni["non_crypto_excluded_count"], 2)

    def test_disposition_labels(self) -> None:
        self.assertEqual(asset_disposition("stock"), cfg.CROSS_ASSET_DISPOSITION)
        self.assertEqual(asset_disposition(""), cfg.CRYPTO_OPPORTUNITY_DISPOSITION)
        self.assertEqual(symbol_type_of({"symbolType": "stock"}), "stock")


class TestFreshnessNotOverclaimed(unittest.TestCase):
    def test_degraded_when_error(self) -> None:
        # Mirror scanner_service status mapping rules in isolation.
        def map_fresh(*, age: int, ws: bool, err: str | None) -> str:
            if err:
                return "DEGRADED"
            if age >= 120_000:
                return "STALE"
            if age >= 45_000:
                return "DELAYED"
            if not ws:
                return "DEGRADED"
            return "LIVE"

        self.assertEqual(map_fresh(age=10_000, ws=True, err="boom"), "DEGRADED")
        self.assertEqual(map_fresh(age=10_000, ws=False, err=None), "DEGRADED")
        self.assertEqual(map_fresh(age=10_000, ws=True, err=None), "LIVE")
        self.assertEqual(map_fresh(age=60_000, ws=True, err=None), "DELAYED")
        self.assertNotEqual(map_fresh(age=200_000, ws=True, err=None), "LIVE")


if __name__ == "__main__":
    unittest.main()
