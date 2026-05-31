import unittest

from backend.autonomy.pure_ai_orchestrator import PureAiOrchestrator


class PureAiOrchestratorTests(unittest.TestCase):
    def test_aggressive_sizing_meets_target_notional(self):
        proposal = {"adjusted_confidence": 0.7}
        sized = PureAiOrchestrator.apply_aggressive_sizing(proposal, deployable_pool=5000)
        self.assertGreaterEqual(float(sized["margin"]) * float(sized["leverage"]), 1200.0)
        self.assertGreaterEqual(float(sized["leverage"]), 10.0)

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


if __name__ == "__main__":
    unittest.main()
