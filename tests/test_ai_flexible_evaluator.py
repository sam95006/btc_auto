import unittest
from unittest.mock import MagicMock

from backend.autonomy.ai_flexible_evaluator import AiFlexibleEvaluator
from backend.trading.fee_churn_guard import FeeChurnGuard
from config.sandbox_exit_config import SANDBOX_TP_ABS_USD


class _FakeGateway:
    def __init__(self, outputs):
        self.outputs = dict(outputs)
        self.calls = []

    def enabled(self):
        return True

    def run_task(self, task, payload, fallback_output=None):
        self.calls.append((task, payload))
        return {"status": "ok", "output": self.outputs.get(task, fallback_output or {})}


class AiFlexibleEvaluatorTests(unittest.TestCase):
    def test_collect_trade_proposals_parses_leverage_and_margin(self):
        gateway = _FakeGateway(
            {
                "flex_trade_eval": {
                    "trade_proposals": [
                        {
                            "fleet": "RADAR",
                            "symbol": "WIFUSDT",
                            "side": "BUY",
                            "confidence": 0.78,
                            "leverage": 35,
                            "margin_usd": 120,
                            "rationale": "funding negative + radar momentum",
                        }
                    ]
                }
            }
        )
        evaluator = AiFlexibleEvaluator(llm_gateway=gateway)
        rows = evaluator.collect_trade_proposals({"deployable_pool": 4200, "radar_scan": {}})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ai_flex_leverage"], 35.0)
        self.assertEqual(rows[0]["ai_flex_margin_usd"], 120.0)

    def test_apply_ai_sizing_sets_leverage_and_margin(self):
        evaluator = AiFlexibleEvaluator()
        proposal = {
            "decision_source": "ai_flex_eval",
            "ai_flex_leverage": 50,
            "ai_flex_margin_usd": 150,
        }
        sized = evaluator.apply_ai_sizing(proposal, deployable_pool=4000, max_leverage=100)
        self.assertEqual(sized["leverage"], 50.0)
        self.assertEqual(sized["margin"], 150.0)
        self.assertEqual(sized["sizing_source"], "ai_flex_llm")

    def test_auto_profit_exit_when_pnl_exceeds_target(self):
        evaluator = AiFlexibleEvaluator(llm_gateway=_FakeGateway({}))
        actions = evaluator.evaluate_exit_actions(
            [
                {
                    "symbol": "ETHUSDT",
                    "fleet": "ETH",
                    "unrealized_pnl": SANDBOX_TP_ABS_USD + 5,
                    "margin": 80,
                    "leverage": 20,
                }
            ],
            market_contexts={"ETH": {}},
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["source"], "ai_flex_auto_profit")
        self.assertIn("ai_auto_profit", actions[0]["reason"])

    def test_evaluate_exit_actions_filters_low_confidence_llm(self):
        gateway = _FakeGateway(
            {
                "flex_exit_eval": {
                    "exit_actions": [
                        {"symbol": "BTCUSDT", "fleet": "BTC", "decision": "CLOSE", "confidence": 0.50},
                        {"symbol": "ETHUSDT", "fleet": "ETH", "decision": "PARTIAL", "confidence": 0.82, "fraction": 0.4},
                    ]
                }
            }
        )
        evaluator = AiFlexibleEvaluator(llm_gateway=gateway)
        actions = evaluator.evaluate_exit_actions(
            [{"symbol": "BTCUSDT", "fleet": "BTC"}, {"symbol": "ETHUSDT", "fleet": "ETH"}],
            market_contexts={"BTC": {}, "ETH": {}},
        )
        symbols = {item["symbol"] for item in actions}
        self.assertIn("ETHUSDT", symbols)
        self.assertNotIn("BTCUSDT", symbols)

    def test_heuristic_fallback_when_llm_empty(self):
        evaluator = AiFlexibleEvaluator(llm_gateway=_FakeGateway({}))
        rows = evaluator.collect_trade_proposals(
            {
                "core_fleets": {
                    "BTC": {
                        "symbol": "BTCUSDT",
                        "signal": {"action": "BUY", "confidence": 0.72, "reason": "momentum"},
                    }
                },
                "positions": [],
                "blocked_symbols": [],
                "radar_scan": {},
            }
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["proposer"], "ai_flex_heuristic")

    def test_auto_profit_pct_exit(self):
        evaluator = AiFlexibleEvaluator(llm_gateway=_FakeGateway({}))
        actions = evaluator.evaluate_exit_actions(
            [
                {
                    "symbol": "SOLUSDT",
                    "fleet": "SOL",
                    "unrealized_pnl": 6.0,
                    "margin": 40,
                    "leverage": 10,
                }
            ],
            market_contexts={"SOL": {}},
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["source"], "ai_flex_auto_profit")

        guard = FeeChurnGuard()
        position = {
            "id": "p1",
            "opened_at": "2099-01-01 00:00:00",
            "unrealized_pnl": 2.0,
            "margin": 80,
            "leverage": 20,
        }
        for source in ("ai_flex_exit", "ai_flex_auto_profit"):
            allowed, reason = guard.allow_ai_exit(
                position,
                {"source": source, "confidence": 0.75, "reason": "take_profit"},
            )
            self.assertTrue(allowed, source)
            self.assertIsNone(reason)


if __name__ == "__main__":
    unittest.main()
