import unittest

from backend.risk.dynamic_margin_engine import DynamicMarginEngine


class DynamicMarginEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = DynamicMarginEngine()

    def test_confidence_below_threshold_blocks_trade(self):
        result = self.engine.calculate_proposed_margin(0.30)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["margin_mult"], 0.0)

    def test_confidence_bands(self):
        cases = [
            (0.40, 0.45),
            (0.60, 0.55),
            (0.70, 0.70),
            (0.80, 0.90),
            (0.88, 1.15),
            (0.95, 1.50),
        ]
        for confidence, expected_mult in cases:
            with self.subTest(confidence=confidence):
                result = self.engine.calculate_proposed_margin(confidence)
                self.assertTrue(result["allowed"])
                self.assertEqual(result["margin_mult"], expected_mult)


if __name__ == "__main__":
    unittest.main()
