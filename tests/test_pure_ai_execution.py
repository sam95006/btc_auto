import unittest

from backend.autonomy.pure_ai_execution import (
    prepare_pure_ai_execution_request,
    remap_to_tradable_symbol,
)


class PureAiExecutionTests(unittest.TestCase):
    def test_remap_exotic_symbol_to_preferred(self):
        tradable = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
        self.assertEqual(remap_to_tradable_symbol("CCUSDT", tradable), "BTCUSDT")

    def test_prepare_caps_margin_and_strips_pct(self):
        request = prepare_pure_ai_execution_request(
            {
                "decision_source": "pure_ai_trader",
                "symbol": "CCUSDT",
                "side": "BUY",
                "margin_pct_deployable": 0.08,
                "margin": 366.0,
                "leverage": 40,
                "adjusted_confidence": 0.6,
            },
            deployable_pool=5000.0,
            radar_available=450.0,
            futures_client=None,
        )
        self.assertNotIn("_execution_block", request)
        self.assertIn(request["symbol"], {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT"})
        self.assertLessEqual(float(request["margin"]), 120.0)
        self.assertNotIn("margin_pct_deployable", request)


if __name__ == "__main__":
    unittest.main()
