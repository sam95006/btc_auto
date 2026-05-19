import unittest

from backend.risk.dynamic_leverage_engine import DynamicLeverageEngine


class DynamicLeverageEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = DynamicLeverageEngine()

    def test_confidence_below_threshold_blocks_trade(self):
        result = self.engine.calculate_proposed_leverage(0.30)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["proposed_leverage"], 0)

    def test_confidence_bands(self):
        cases = [
            (0.40, 3),
            (0.60, 5),
            (0.70, 10),
            (0.80, 20),
            (0.88, 50),
            (0.95, 100),
        ]
        for confidence, expected in cases:
            with self.subTest(confidence=confidence):
                result = self.engine.calculate_proposed_leverage(confidence)
                self.assertTrue(result["allowed"])
                self.assertEqual(result["proposed_leverage"], expected)


if __name__ == "__main__":
    unittest.main()
