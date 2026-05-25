import unittest

from backend.governance.ai_exit_planner import AiExitPlanner


class AiExitPlannerTests(unittest.TestCase):
    def test_tp_prices_for_long(self):
        planner = AiExitPlanner()
        plan = planner.plan_for_position(
            {
                "symbol": "BTCUSDT",
                "fleet": "BTC",
                "side": "BUY",
                "entry_price": 76956.25,
                "mark_price": 77346.30,
                "quantity": 0.0074,
                "margin": 113.67,
                "unrealized_pnl": 2.71,
                "r_exit_state": {"risk_r_usd": 11.367, "tp1_done": False},
            }
        )
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan["tp_levels"]), 3)
        self.assertGreater(plan["tp_levels"][0]["target_price"], plan["entry_price"])

    def test_pnl_r_below_tp1_by_default(self):
        planner = AiExitPlanner()
        plan = planner.plan_for_position(
            {
                "symbol": "BTCUSDT",
                "fleet": "BTC",
                "side": "BUY",
                "entry_price": 76956.25,
                "quantity": 0.0074,
                "margin": 113.67,
                "unrealized_pnl": 2.71,
            }
        )
        self.assertLess(plan["pnl_r"], 1.0)
        self.assertFalse(plan["tp_levels"][0]["hit"])


if __name__ == "__main__":
    unittest.main()
