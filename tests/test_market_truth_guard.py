import unittest

from backend.market.market_context_service import MarketContextService


class MarketTruthGuardTests(unittest.TestCase):
    def test_truth_layer_marks_stale_price(self):
        service = MarketContextService()
        status = service.build_truth_layer_status(
            prices={"BTC": {"price": 100.0, "time": "2000-01-01T00:00:00", "source": "test"}},
            spot_account={"update_time": 0},
            futures_account={"update_time": 0},
            account_sync_status={"spot_stream_health": {}},
            market_contexts={},
        )
        self.assertFalse(status["fresh_for_ai"])
        self.assertIn("btc_price_stale", status["stale_reasons"])

    def test_truth_layer_marks_fresh_snapshot(self):
        service = MarketContextService()
        now = "2099-01-01T00:00:00"
        status = service.build_truth_layer_status(
            prices={"BTC": {"price": 100.0, "time": now, "source": "test"}},
            spot_account={"update_time": 4070908800000},
            futures_account={"update_time": 4070908800000},
            account_sync_status={"spot_stream_health": {"last_event_time": 4070908800000}},
            market_contexts={"BTC": {"spread_status": "normal", "liquidity_status": "healthy"}},
        )
        self.assertTrue(status["fresh_for_ai"])
        self.assertEqual(status["stale_reasons"], [])

