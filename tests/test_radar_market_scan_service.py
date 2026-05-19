import unittest

from backend.market.radar_market_scan_service import RadarMarketScanService


class _StubFuturesClient:
    def is_configured(self):
        return True


class _StubMarketContextService:
    def build_symbol_context(self, symbol, price_payload=None, position_payload=None, fleet=None):
        return {
            "symbol": symbol,
            "spread_status": "normal",
            "liquidity_status": "healthy",
            "slippage_risk": "normal",
            "funding_risk": "normal",
            "basis_risk": "normal",
            "oi_notional_status": "healthy",
            "top5_cross_notional": 250000.0,
            "order_book_imbalance": 0.42,
            "imbalance_bias": "bid",
            "funding_rate": -0.0005,
            "basis_bps": -8.0,
            "liquidation_risk": "none",
            "market_regime": "normal",
            "spread_bps": 2.4,
        }


class RadarMarketScanServiceTests(unittest.TestCase):
    def test_scan_builds_candidates(self):
        service = RadarMarketScanService(
            futures_client=_StubFuturesClient(),
            market_context_service=_StubMarketContextService(),
            symbols=("BTCUSDT", "ETHUSDT"),
            cache_seconds=1,
        )
        snapshot = service.scan()
        self.assertEqual(snapshot["scan_status"], "ok")
        self.assertTrue(snapshot["candidates"])
        self.assertIn("whale_watch", snapshot)


if __name__ == "__main__":
    unittest.main()
