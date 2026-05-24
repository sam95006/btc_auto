import unittest
from unittest.mock import MagicMock

from backend.market.market_price_feed_service import MarketPriceFeedService
from backend.monitoring.trading_health_service import TradingHealthService
from backend.news.event_registry import EventRegistry
from config.autonomy_config import NEXUS_AUTONOMY_LEVEL, NEXUS_SHADOW_MODE
from config.llm_config import llm_enabled


class SystemUpgradeV2Tests(unittest.TestCase):
    def test_futures_prices_preferred_when_client_configured(self):
        client = MagicMock()
        client.is_configured.return_value = True
        client.resolve_symbol.side_effect = lambda fleet: {
            "BTC": "BTCUSDT",
            "ETH": "ETHUSDT",
            "SOL": "SOLUSDT",
            "BNB": "BNBUSDT",
            "PEPE": "1000PEPEUSDT",
        }.get(fleet, f"{fleet}USDT")
        client.fetch_24h_tickers.return_value = [
            {"symbol": "BTCUSDT", "lastPrice": "70000.1"},
            {"symbol": "ETHUSDT", "lastPrice": "2100.2"},
        ]

        feed = MarketPriceFeedService()
        prices = feed.get_prices(client)
        self.assertEqual(prices["BTC"]["source"], "binance_futures_testnet")
        self.assertEqual(prices["BTC"]["price"], 70000.1)

    def test_trading_health_scores_dimensions(self):
        service = TradingHealthService()
        report = service.build_report(
            {
                "system": {"trading_paused": False},
                "growth_mode": {"block_new_entries": False},
                "truth_layer_status": {"futures_ready_for_ai": True},
                "llm_status": {"enabled": True, "providers_ready": True},
                "live_sync": {
                    "price_sources": {"BTC": "binance_futures_testnet"},
                    "news_count": 5,
                },
                "learning_status": {"learning_reviews": {"auto_apply": True}},
                "event_registry": {"event_count": 4},
                "decision_audit": [
                    {"approved": 1},
                    {"approved": 0, "reject_reason": "quality_below_growth_threshold"},
                ],
            }
        )
        self.assertGreaterEqual(report["overall_score"], 75)
        self.assertIn("dimensions", report)
        self.assertTrue(report["top_reject_reasons"])

    def test_event_registry_fleet_hints(self):
        registry = EventRegistry()
        registry.register_batch(
            [
                {
                    "event_id": "evt-1",
                    "event_type": "macro_risk",
                    "headline": "CPI hotter than expected",
                    "targets": ["BTC"],
                    "major": True,
                }
            ]
        )
        snap = registry.snapshot()
        self.assertTrue(snap.get("fleet_action_hints"))
        self.assertEqual(snap["fleet_action_hints"][0]["bias"], "defensive")

    def test_bold_defaults_autonomy_and_llm(self):
        self.assertGreaterEqual(int(NEXUS_AUTONOMY_LEVEL or 1), 2)
        self.assertFalse(NEXUS_SHADOW_MODE)


if __name__ == "__main__":
    unittest.main()
