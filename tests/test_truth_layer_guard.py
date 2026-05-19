import unittest

from backend.market.truth_layer_guard import TruthLayerGuard


class TruthLayerGuardTests(unittest.TestCase):
    def setUp(self):
        self.guard = TruthLayerGuard()

    def test_stale_spot_blocks_spot_ai(self):
        result = self.guard.evaluate(
            {
                "spot_account_freshness": {"status": "stale"},
                "futures_account_freshness": {"status": "fresh"},
                "price_freshness": {"BTC": {"status": "fresh"}},
                "degraded_market_contexts": [],
                "stale_reasons": ["spot_account_stale"],
            },
            {
                "rest_snapshot_status": {"spot": "ok", "futures": "ok"},
                "spot_stream_health": {"status": "connected"},
                "websocket_status": {"futures": "connected"},
            },
            fleet_symbols=["BTC"],
            spot_symbols=["BTC"],
        )
        self.assertFalse(result["spot_ready_for_ai"])
        self.assertTrue(result["futures_ready_for_ai"])

    def test_stale_futures_blocks_futures_ai(self):
        result = self.guard.evaluate(
            {
                "spot_account_freshness": {"status": "fresh"},
                "futures_account_freshness": {"status": "stale"},
                "price_freshness": {"BTC": {"status": "fresh"}},
                "degraded_market_contexts": [],
                "stale_reasons": ["futures_account_stale"],
            },
            {
                "rest_snapshot_status": {"spot": "ok", "futures": "ok"},
                "spot_stream_health": {"status": "connected"},
                "websocket_status": {"futures": "connected"},
            },
            fleet_symbols=["BTC"],
            spot_symbols=["BTC"],
        )
        self.assertTrue(result["spot_ready_for_ai"])
        self.assertFalse(result["futures_ready_for_ai"])

    def test_too_many_degraded_contexts_blocks_futures(self):
        result = self.guard.evaluate(
            {
                "spot_account_freshness": {"status": "fresh"},
                "futures_account_freshness": {"status": "fresh"},
                "price_freshness": {"BTC": {"status": "fresh"}, "ETH": {"status": "fresh"}, "SOL": {"status": "fresh"}},
                "degraded_market_contexts": ["BTC", "ETH", "SOL"],
                "stale_reasons": [],
            },
            {
                "rest_snapshot_status": {"spot": "ok", "futures": "ok"},
                "spot_stream_health": {"status": "connected"},
                "websocket_status": {"futures": "connected"},
            },
            fleet_symbols=["BTC", "ETH", "SOL"],
            spot_symbols=["BTC"],
        )
        self.assertFalse(result["futures_ready_for_ai"])
        self.assertIn("too_many_degraded_market_contexts", result["stale_reasons"])


if __name__ == "__main__":
    unittest.main()
