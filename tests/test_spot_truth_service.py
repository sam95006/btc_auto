import unittest

from backend.market.spot_truth_service import SpotTruthService


class SpotTruthServiceTests(unittest.TestCase):
    def test_stable_only_truth_mode_keeps_total_on_managed_stables(self):
        service = SpotTruthService(
            truth_mode="stable_only",
            truth_stable_assets=("USDT", "USDC"),
            visible_holdings=("BTC", "ETH"),
        )
        balances = {
            "USDT": {"free": 5000.0, "locked": 0.0},
            "USDC": {"free": 5000.0, "locked": 1.45},
            "BTC": {"free": 0.1, "locked": 0.0},
        }
        prices = {"BTC": {"price": 80000.0}}
        view = service.build_view(balances, prices)
        self.assertEqual(view["spot_total"], 10001.45)
        self.assertEqual(view["stable_total"], 10001.45)
        self.assertAlmostEqual(view["visible_holdings_total"], 8000.0)
        self.assertEqual(view["truth_mode"], "stable_only")

    def test_allowed_assets_scope_filters_unmanaged_assets(self):
        service = SpotTruthService(
            truth_mode="stable_only",
            truth_stable_assets=("USDT", "USDC"),
            visible_holdings=("BTC",),
            allowed_assets=("USDT", "USDC", "BTC"),
        )
        balances = {
            "USDT": {"free": 5000.0, "locked": 0.0},
            "USDC": {"free": 5000.0, "locked": 0.0},
            "DOGE": {"free": 1000.0, "locked": 0.0},
        }
        view = service.build_view(balances, {})
        self.assertEqual(view["spot_total"], 10000.0)
        self.assertEqual(view["excluded_assets_count"], 1)
        self.assertEqual(view["allowed_assets"], ["USDT", "USDC", "BTC"])


if __name__ == "__main__":
    unittest.main()
