import unittest

from backend.portfolio import PortfolioGovernor


class PortfolioGovernorTests(unittest.TestCase):
    def test_builds_restrictions_and_capital_adjustments(self):
        governor = PortfolioGovernor()
        payload = governor.evaluate(
            futures_account={
                "margin_total": 1000.0,
                "positions": [
                    {"fleet": "BTC", "symbol": "BTCUSDT", "side": "SELL", "mark_price": 80000.0, "quantity": 0.003},
                    {"fleet": "ETH", "symbol": "ETHUSDT", "side": "SELL", "mark_price": 2500.0, "quantity": 1.0},
                ],
            },
            market_context={
                "BTC": {"symbol": "BTCUSDT", "market_regime": "normal"},
                "ETH": {"symbol": "ETHUSDT", "market_regime": "thin_liquidity"},
            },
            radar_scan={"candidates": [{"symbol": "BTCUSDT", "candidate_side": "SHORT", "candidate_score": 75.0}]},
            learning_snapshot={"fleet_adjustments": {"BTC": {"aggression_multiplier": 0.9}, "ETH": {"leverage_cap": 3}}},
        )
        self.assertIn("fleet_restrictions", payload)
        self.assertIn("capital_adjustments", payload)
        self.assertIn("BTC", payload["capital_adjustments"])
        self.assertIn("ETH", payload["fleet_restrictions"])
        self.assertIn("correlation_groups", payload)
        self.assertIn("theme_exposures", payload)

    def test_builds_hedge_recommendation_when_concentrated(self):
        governor = PortfolioGovernor()
        payload = governor.evaluate(
            futures_account={
                "margin_total": 1000.0,
                "positions": [
                    {"fleet": "BTC", "symbol": "BTCUSDT", "side": "BUY", "mark_price": 80000.0, "quantity": 0.005},
                    {"fleet": "ETH", "symbol": "ETHUSDT", "side": "BUY", "mark_price": 2500.0, "quantity": 2.0},
                ],
            },
            market_context={
                "BTC": {"symbol": "BTCUSDT", "market_regime": "normal"},
                "ETH": {"symbol": "ETHUSDT", "market_regime": "normal"},
            },
        )
        self.assertTrue(payload["hedge_recommendations"])
        self.assertGreater(payload["correlation_concentration"], 0)


if __name__ == "__main__":
    unittest.main()
