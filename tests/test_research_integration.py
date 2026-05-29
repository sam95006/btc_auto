import os
import unittest
from importlib import reload
from unittest.mock import MagicMock


class ResearchIntegrationTests(unittest.TestCase):
    def test_kline_backtest_approves_with_mock_klines(self):
        os.environ["NEXUS_KLINE_BACKTEST_ENABLED"] = "1"
        import config.backtest_config as cfg
        import backend.analytics.kline_backtest_engine as mod

        reload(cfg)
        reload(mod)
        client = MagicMock()
        closes = [100.0 + i * 0.5 for i in range(80)]
        client.get_klines.return_value = [[0, 0, 0, 0, price, 0] for price in closes]
        engine = mod.KlineBacktestEngine(futures_client=client)
        result = engine.evaluate("BTCUSDT", "BUY")
        self.assertEqual(result["stage"], "kline_research")
        self.assertIn("approved", result)

    def test_walk_forward_oos_pass_flag(self):
        from backend.analytics.walk_forward_evaluator import WalkForwardEvaluator

        rows = []
        for index in range(40):
            rows.append({"pnl": 1.0 if index % 2 == 0 else -0.2})
        status = WalkForwardEvaluator(window_size=10, step_size=5).evaluate(rows)
        self.assertTrue(status.get("ready"))
        self.assertIn("oos_pass", status)

    def test_tradingview_webhook_parses_payload(self):
        os.environ["NEXUS_TRADINGVIEW_WEBHOOK_ENABLED"] = "1"
        os.environ.pop("NEXUS_TRADINGVIEW_WEBHOOK_SECRET", None)
        import config.execution_enhancements_config as excfg
        import backend.api.tradingview_webhook as wh

        reload(excfg)
        reload(wh)
        ok, proposal, reason = wh.parse_tradingview_payload(
            {"symbol": "ETHUSDT", "side": "buy", "confidence": 0.62}
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        self.assertEqual(proposal["symbol"], "ETHUSDT")
        self.assertEqual(proposal["side"], "BUY")

    def test_research_gate_blocks_learning_when_fail(self):
        os.environ["NEXUS_LEARNING_REQUIRE_RESEARCH_PASS"] = "1"
        from backend.learning.learning_review_queue import LearningReviewQueue

        store = MagicMock()
        store.recent_trade_results.return_value = [{"pnl": -5.0}] * 5
        queue = LearningReviewQueue(store)
        with unittest.mock.patch(
            "backend.analytics.research_gate_service.ResearchGateService.build_status",
            return_value={"learning_auto_apply_allowed": False, "reason": "walk_forward_fail"},
        ):
            store.update_learning_review_status = MagicMock()
            result = queue.apply_item(
                {
                    "id": 1,
                    "recommendation": {"fleet": "BTC", "strategy_key": "test"},
                }
            )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
