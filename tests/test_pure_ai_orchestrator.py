import unittest

from backend.autonomy.pure_ai_orchestrator import PureAiOrchestrator


class PureAiOrchestratorTests(unittest.TestCase):
    def test_aggressive_sizing_caps_margin_and_strips_pct(self):
        proposal = {
            "adjusted_confidence": 0.7,
            "margin_pct_deployable": 0.08,
        }
        sized = PureAiOrchestrator.apply_aggressive_sizing(
            proposal,
            deployable_pool=5000,
            radar_available=450.0,
        )
        self.assertNotIn("margin_pct_deployable", sized)
        self.assertLessEqual(float(sized["margin"]), 120.0)
        self.assertGreaterEqual(float(sized["leverage"]), 10.0)
        self.assertEqual(sized.get("sizing_source"), "pure_ai_aggressive")

    def test_stale_safety_exit_after_hours(self):
        orchestrator = PureAiOrchestrator(llm_gateway=None)
        rows = orchestrator._stale_safety_exits(
            [
                {
                    "symbol": "ETHUSDT",
                    "fleet": "ETH",
                    "opened_at": "2000-01-01 00:00:00",
                }
            ],
            existing=[],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "pure_ai_safety")

    def test_llm_only_keeps_liquid_heartbeat_proposals(self):
        class _Eval:
            entry_enabled = True
            exit_enabled = False

            def collect_trade_proposals(self, context):
                return [
                    {
                        "fleet": "BTC",
                        "symbol": "BTCUSDT",
                        "side": "BUY",
                        "adjusted_confidence": 0.28,
                        "margin": 90,
                        "leverage": 20,
                        "decision_source": "pure_ai_liquid_heartbeat",
                        "proposer": "pure_ai_liquid_heartbeat",
                    }
                ]

            def evaluate_exit_actions(self, *args, **kwargs):
                return []

        orchestrator = PureAiOrchestrator(llm_gateway=None)
        orchestrator.evaluator = _Eval()
        rows, _policy = orchestrator._collect_entries(
            {
                "deployable_pool": 4000.0,
                "radar_budget_available": 400.0,
                "positions": [],
                "core_fleets": {},
            }
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "BTCUSDT")
        self.assertEqual(rows[0]["decision_source"], "pure_ai_trader")

    def test_pyramid_add_on_winning_position(self):
        orchestrator = PureAiOrchestrator(llm_gateway=None)
        context = {
            "deployable_pool": 4000.0,
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "fleet": "BTC",
                    "side": "BUY",
                    "margin": 100.0,
                    "unrealized_pnl": 20.0,
                    "leverage": 20,
                    "entry_price": 100.0,
                    "mark_price": 101.5,
                }
            ],
        }
        rows = orchestrator._collect_pyramid_adds(context, existing=[])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].get("pyramid_add"))
        self.assertEqual(rows[0]["side"], "BUY")
        self.assertEqual(rows[0]["symbol"], "BTCUSDT")


if __name__ == "__main__":
    unittest.main()
