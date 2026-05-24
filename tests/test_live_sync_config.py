import time
import unittest
from unittest.mock import patch

from backend.market.market_price_feed_service import MarketPriceFeedService
from config.live_sync_config import (
    EXCHANGE_REFRESH_MIN_SECONDS,
    GLOBAL_INDEX_REFRESH_SECONDS,
    NEWS_REFRESH_SECONDS,
    WS_PUSH_INTERVAL_SECONDS,
)


class LiveSyncConfigTests(unittest.TestCase):
    def test_defaults_are_positive(self):
        self.assertGreaterEqual(EXCHANGE_REFRESH_MIN_SECONDS, 1.0)
        self.assertGreaterEqual(NEWS_REFRESH_SECONDS, 30)
        self.assertGreaterEqual(WS_PUSH_INTERVAL_SECONDS, 0.5)
        self.assertGreaterEqual(GLOBAL_INDEX_REFRESH_SECONDS, 15)


class MarketOverviewCacheTests(unittest.TestCase):
    def test_get_market_overview_respects_ttl(self):
        feed = MarketPriceFeedService()
        feed.last_market_overview = {"source": "test-cache", "indices": {}}
        feed._last_overview_at = time.time()

        with patch.object(feed, "fetch_market_overview") as fetch:
            cached = feed.get_market_overview(max_age_seconds=60)
            fetch.assert_not_called()
        self.assertEqual(cached.get("source"), "test-cache")

        with patch.object(feed, "fetch_market_overview", return_value={"source": "fresh", "indices": {}}) as fetch:
            fresh = feed.get_market_overview(max_age_seconds=60, force=True)
            fetch.assert_called_once()
        self.assertEqual(fresh.get("source"), "fresh")


if __name__ == "__main__":
    unittest.main()
