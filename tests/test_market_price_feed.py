import unittest
from unittest.mock import patch

from backend.market.market_price_feed_service import MarketPriceFeedService


class MarketPriceFeedTests(unittest.TestCase):
    def test_market_line_payload_has_price_after_yahoo(self):
        service = MarketPriceFeedService()
        with patch.object(service, "_fetch_yahoo_chart", return_value={"price": 100.0, "change": 1.0, "change_pct": 1.0, "quote_source": "yahoo_chart"}):
            with patch.object(service, "_fetch_stooq_quote", side_effect=ValueError("skip")):
                overview = service.fetch_market_overview()
        self.assertIsNotNone(overview["indices"]["spx"]["price"])
        self.assertEqual(overview["indices"]["spx"]["price"], 100.0)

    def test_stooq_parser(self):
        service = MarketPriceFeedService()
        csv_body = "Symbol,Date,Time,Open,High,Low,Close,Volume\n^SPX,2026-05-20,23:00:00,7369.2,7435.7,7357.5,7433,1\n"
        with patch("backend.market.market_price_feed_service.urlopen") as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = csv_body.encode("utf-8")
            data = service._fetch_stooq_quote("^spx")
        self.assertEqual(data["price"], 7433.0)
        self.assertEqual(data["quote_source"], "stooq")

    def test_seed_cache_used_when_providers_fail(self):
        service = MarketPriceFeedService()
        service.seed_index_cache(
            {
                "spx": {
                    "label": "標普 500",
                    "price": 7400.0,
                    "change_pct": 0.5,
                    "direction": "漲",
                    "quote_source": "yahoo_chart",
                }
            }
        )
        with patch.object(service, "_fetch_yahoo_chart", side_effect=OSError("blocked")):
            with patch.object(service, "_fetch_stooq_quote", side_effect=OSError("blocked")):
                overview = service.fetch_market_overview()
        self.assertEqual(overview["indices"]["spx"]["price"], 7400.0)
        self.assertTrue(str(overview["indices"]["spx"].get("quote_source", "")).endswith("_stale"))


if __name__ == "__main__":
    unittest.main()
