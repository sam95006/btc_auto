import os
import unittest

os.environ["NEXUS_PURE_AI_MODE"] = "1"
os.environ["NEXUS_TESTNET_SANDBOX"] = "1"

from backend.autonomy.pure_ai_hard_exit import collect_pure_ai_hard_exits


class PureAiHardExitTests(unittest.TestCase):
    def test_partial_take_profit_on_green(self):
        rows = collect_pure_ai_hard_exits(
            [
                {
                    "symbol": "LRCUSDT",
                    "fleet": "RADAR",
                    "margin": 80.0,
                    "quantity": 1000,
                    "unrealized_pnl": 12.0,
                }
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], "take_partial_profit")
        self.assertEqual(rows[0]["fraction"], 0.5)

    def test_full_stop_on_deep_loss(self):
        rows = collect_pure_ai_hard_exits(
            [
                {
                    "symbol": "XMRUSDT",
                    "fleet": "RADAR",
                    "margin": 80.0,
                    "quantity": 1000,
                    "unrealized_pnl": -161.0,
                }
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], "reduce_or_close")
        self.assertEqual(rows[0]["source"], "pure_ai_hard_exit")


if __name__ == "__main__":
    unittest.main()
