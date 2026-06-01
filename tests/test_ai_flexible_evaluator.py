import os
import unittest
from unittest.mock import MagicMock

os.environ["NEXUS_PURE_AI_MODE"] = "0"

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
    def setUp(self):
        self._prev_pure_ai = os.environ.get("NEXUS_PURE_AI_MODE")
        os.environ["NEXUS_PURE_AI_MODE"] = "0"

    def tearDown(self):
        if self._prev_pure_ai is None:
            os.environ.pop("NEXUS_PURE_AI_MODE", None)
        else:
            os.environ["NEXUS_PURE_AI_MODE"] = self._prev_pure_ai

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

    def test_pure_ai_liquid_heartbeat_when_llm_and_radar_empty(self):
        from unittest.mock import patch

        os.environ["NEXUS_PURE_AI_MODE"] = "1"
        try:
            evaluator = AiFlexibleEvaluator(llm_gateway=_FakeGateway({}))
            with patch("config.pure_ai_trading_config.PURE_AI_RADAR_FALLBACK", False), patch(
                "config.pure_ai_trading_config.PURE_AI_REQUIRE_MIN_PROPOSALS", True
            ), patch("config.pure_ai_trading_config.PURE_AI_HEURISTIC_HEARTBEAT", False):
                rows = evaluator.collect_trade_proposals(
                {
                    "pure_ai_mode": True,
                    "deployable_pool": 3000,
                    "positions": [],
                    "blocked_symbols": [],
                    "radar_scan": {"candidates": []},
                    "tradable_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
                    "core_fleets": {},
                    "market_context": {},
                }
                )
            self.assertGreaterEqual(len(rows), 1)
            self.assertEqual(rows[0].get("proposer"), "pure_ai_liquid_heartbeat")
            self.assertEqual(evaluator._last_entry_eval.get("fallback_used"), "liquid_heartbeat")
        finally:
            os.environ["NEXUS_PURE_AI_MODE"] = "0"

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

    def test_stale_position_profit_exit(self):
        evaluator = AiFlexibleEvaluator(llm_gateway=_FakeGateway({}))
        actions = evaluator._auto_profit_exit_candidates(
            [
                {
                    "symbol": "ETHUSDT",
                    "fleet": "ETH",
                    "unrealized_pnl": 6.0,
                    "margin": 80,
                    "leverage": 10,
                    "opened_at": "2000-01-01 00:00:00",
                }
            ]
        )
        self.assertEqual(len(actions), 1)
        self.assertIn("ai_auto_profit", actions[0]["reason"])

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
