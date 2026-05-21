import unittest

from backend.market.spot_truth_service import SpotTruthService


class SpotTruthTests(unittest.TestCase):
    def test_stable_only_counts_usdt_usdc(self):
        service = SpotTruthService(truth_mode="stable_only")
        view = service.build_view(
            {
                "USDT": {"free": 5000.0, "locked": 0.0},
                "USDC": {"free": 5000.0, "locked": 0.0},
                "BTC": {"free": 99.0, "locked": 0.0},
            },
            {"BTC": {"price": 60000.0}},
        )
        self.assertEqual(view["spot_total"], 10000.0)
        self.assertEqual(view["usdt_total"], 5000.0)
        self.assertEqual(view["usdc_total"], 5000.0)
        self.assertEqual(view["visible_holdings_total"], 99.0 * 60000.0)


if __name__ == "__main__":
    unittest.main()
