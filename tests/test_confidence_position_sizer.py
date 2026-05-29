import unittest

from backend.risk.confidence_position_sizer import ConfidencePositionSizer


class ConfidencePositionSizerTests(unittest.TestCase):
    def test_low_confidence_smaller_than_high(self):
        sizer = ConfidencePositionSizer(min_confidence=0.4)
        low = sizer.compute(0.45, fleet="RADAR")
        high = sizer.compute(0.95, fleet="RADAR")
        self.assertLess(low["margin_multiplier"], high["margin_multiplier"])
        self.assertLess(low["leverage"], high["leverage"])
        self.assertLess(low["margin"], high["margin"])

    def test_apply_sets_metadata(self):
        sizer = ConfidencePositionSizer()
        proposal = {
            "fleet": "RADAR",
            "symbol": "DOGEUSDT",
            "side": "BUY",
            "raw_confidence": 0.82,
            "decision_source": "llm_proposer",
            "strategy_key": "ai_led_trade_proposer",
        }
        out = sizer.apply(proposal, deployable_pool=1000.0)
        self.assertTrue(out.get("confidence_sizing_applied"))
        self.assertIn("confidence_tier", out.get("confidence_sizing") or {})
        self.assertGreater(out.get("margin", 0), 0)
        self.assertGreater(out.get("leverage", 0), 0)


if __name__ == "__main__":
    unittest.main()
