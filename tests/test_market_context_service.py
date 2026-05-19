import unittest

from backend.market.market_context_service import MarketContextService


class _FakeFuturesClient:
    def is_configured(self):
        return True

    def get_order_book(self, symbol, limit=20):
        return {
            "bids": [["100", "10"], ["99.5", "12"]],
            "asks": [["100.5", "8"], ["101", "10"]],
        }

    def get_book_ticker(self, symbol):
        return {"bidPrice": "100", "askPrice": "100.5"}

    def get_premium_index(self, symbol):
        return {"markPrice": "100.4", "indexPrice": "100.0", "lastFundingRate": "0.0001"}

    def get_open_interest(self, symbol):
        return {"openInterest": "250000"}


class MarketContextServiceTests(unittest.TestCase):
    def test_build_futures_context_contains_extended_perception_fields(self):
        service = MarketContextService(futures_client=_FakeFuturesClient())
        contexts = service.build_futures_contexts(
            {"BTC": "BTCUSDT"},
            {"BTC": {"price": 100.25}},
            futures_account={"positions": [{"symbol": "BTCUSDT", "signed_quantity": -1, "liquidation_price": 95.0}]},
        )
        payload = contexts["BTC"]
        for key in (
            "basis_bps",
            "basis_risk",
            "funding_risk",
            "order_book_imbalance",
            "estimated_buy_slippage_bps",
            "estimated_sell_slippage_bps",
            "worst_slippage_bps",
            "slippage_risk",
            "oi_notional_status",
            "liquidation_distance_pct",
            "liquidation_risk",
        ):
            self.assertIn(key, payload)


if __name__ == "__main__":
    unittest.main()
