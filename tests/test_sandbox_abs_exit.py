import os
import unittest
from unittest.mock import patch

from backend.trading.r_exit_engine import RExitEngine


class SandboxAbsExitTests(unittest.TestCase):
    def setUp(self):
        self.engine = RExitEngine()

    @patch("backend.trading.r_exit_engine.SANDBOX_TP_ABS_USD", 25.0)
    @patch("backend.trading.r_exit_engine.SANDBOX_ABS_EXIT_ENABLED", True)
    @patch("backend.trading.r_exit_engine.sandbox_active", return_value=True)
    def test_sandbox_abs_take_profit(self, *_mocks):
        position = {
            "side": "BUY",
            "margin": 100.0,
            "unrealized_pnl": 30.0,
            "r_exit_state": {"risk_r_usd": 12.0, "tp1_done": False, "tp2_done": False, "tp3_done": False},
        }
        action = self.engine.evaluate(position, 100.0, signal={"action": "HOLD", "confidence": 0.0})
        self.assertIsNotNone(action)
        self.assertEqual(action["reason"], "sandbox_abs_take_profit")
        self.assertEqual(action["type"], "full")

    @patch("backend.trading.r_exit_engine.SANDBOX_SL_ABS_USD", 15.0)
    @patch("backend.trading.r_exit_engine.SANDBOX_ABS_EXIT_ENABLED", True)
    @patch("backend.trading.r_exit_engine.sandbox_active", return_value=True)
    def test_sandbox_abs_stop_loss(self, *_mocks):
        position = {
            "side": "BUY",
            "margin": 100.0,
            "unrealized_pnl": -20.0,
            "r_exit_state": {"risk_r_usd": 12.0, "tp1_done": False, "tp2_done": False, "tp3_done": False},
        }
        action = self.engine.evaluate(position, 100.0, signal={"action": "HOLD", "confidence": 0.0})
        self.assertIsNotNone(action)
        self.assertEqual(action["reason"], "sandbox_abs_stop_loss")


if __name__ == "__main__":
    unittest.main()
