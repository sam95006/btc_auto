import unittest
from unittest.mock import MagicMock, patch

from backend.market.binance_macro_market_service import BinanceMacroMarketService
from backend.market.external_market_intel_service import ExternalMarketIntelService
from backend.market.fear_greed_market_service import FearGreedMarketService


class FearGreedServiceTests(unittest.TestCase):
    def test_classifies_extreme_fear(self):
        http = MagicMock()
        http.get_json.return_value = {"data": [{"value": "18", "timestamp": "1"}]}
        svc = FearGreedMarketService(http=http)
        out = svc.fetch_index()
        self.assertTrue(out["ok"])
        self.assertEqual(out["classification"], "extreme_fear")
        self.assertTrue(out["extreme_fear"])


class ExternalIntelMergeTests(unittest.TestCase):
    def test_apply_to_contexts_merges_supplementary_fields(self):
        intel = ExternalMarketIntelService(
            coingecko=MagicMock(configured=lambda: False, fetch_top_markets=lambda: {"ok": False}),
            coinmarketcap=MagicMock(configured=lambda: False, fetch_global_metrics=lambda: {"ok": False}),
            cryptoquant=MagicMock(configured=lambda: False, fetch_risk_signals=lambda: {"ok": False}),
            fear_greed=MagicMock(
                configured=lambda: True,
                fetch_index=lambda: {
                    "ok": True,
                    "value": 22,
                    "classification": "extreme_fear",
                    "extreme_fear": True,
                    "extreme_greed": False,
                },
            ),
            binance_macro=MagicMock(
                configured=lambda: True,
                fetch_btc_macro=lambda: {
                    "ok": True,
                    "long_short_account_ratio": 0.71,
                    "liquidation_stress": True,
                    "long_crowded": True,
                    "spot_futures_premium_bps": 12.0,
                },
            ),
        )
        intel._last_snapshot = intel.refresh()
        ctx = intel.apply_to_contexts({"BTC": {"symbol": "BTCUSDT"}})
        self.assertTrue(ctx["BTC"]["fear_greed_extreme_fear"])
        self.assertTrue(ctx["BTC"]["btc_liquidation_stress"])
        self.assertEqual(ctx["BTC"]["btc_long_short_ratio"], 0.71)


class BinanceMacroServiceTests(unittest.TestCase):
    def test_long_crowded_flag(self):
        futures = MagicMock()
        futures.is_configured.return_value = True
        futures.get_premium_index.return_value = {"markPrice": "100", "indexPrice": "99"}
        futures.get_open_interest.return_value = {"openInterest": "1000"}
        futures.get_futures_market_data.return_value = [{"longShortRatio": "0.65"}]
        futures.get_recent_liquidation_orders.return_value = [{}] * 15

        svc = BinanceMacroMarketService(futures_client=futures, spot_client=None)
        with patch("backend.market.binance_macro_market_service.BINANCE_MACRO_ENABLED", True):
            out = svc.fetch_btc_macro()
        self.assertTrue(out["liquidation_stress"])
        self.assertTrue(out["long_crowded"])


if __name__ == "__main__":
    unittest.main()
