import os
import unittest
from unittest.mock import patch

from backend.fleets.base_strategy_engine import BaseFleetStrategyEngine


class _FakeExecutionEngine:
    def recent_trades(self, limit=100):
        return []

    def close_position(self, *args, **kwargs):
        return {"ok": True}


class _FakePositionManager:
    def get_by_fleet(self, fleet):
        return []


class _FakeLedger:
    def snapshot(self):
        return {
            "fleets": {
                "BTC": {"available": 200.0, "allocated": 200.0},
            }
        }


class _FakeRiskEngine:
    def __init__(self):
        self.ledger = _FakeLedger()


class _FakeLearningFeedback:
    def __init__(self, guidance):
        self.guidance = guidance

    def get_strategy_guidance(self, fleet, strategy_key, market_regime=None, market_context=None):
        return dict(self.guidance)


class BaseStrategyLearningControlsTests(unittest.TestCase):
    def setUp(self):
        self._sandbox_env = patch.dict(os.environ, {"NEXUS_TESTNET_SANDBOX": "0"}, clear=False)
        self._sandbox_env.start()

    def tearDown(self):
        self._sandbox_env.stop()

    def test_symbol_cooldown_blocks_new_request(self):
        engine = BaseFleetStrategyEngine(
            "BTC",
            _FakeExecutionEngine(),
            _FakePositionManager(),
            _FakeRiskEngine(),
            event_bus=None,
            learning_feedback=_FakeLearningFeedback(
                {
                    "symbol_cooldown": {"BTCUSDT": {"active": True}},
                    "min_confidence_threshold": 0.35,
                    "confidence_penalty": 0.0,
                    "aggression_multiplier": 1.0,
                    "position_size_multiplier": 1.0,
                }
            ),
        )
        request = engine.build_open_request({"action": "BUY", "reason": "x", "confidence": 0.8}, 100.0, market_context={"market_regime": "normal"})
        self.assertIsNone(request)
        self.assertEqual(engine.last_reason, "learning_symbol_cooldown")

    def test_learning_raises_confidence_gate_and_scales_margin(self):
        engine = BaseFleetStrategyEngine(
            "BTC",
            _FakeExecutionEngine(),
            _FakePositionManager(),
            _FakeRiskEngine(),
            event_bus=None,
            learning_feedback=_FakeLearningFeedback(
                {
                    "symbol_cooldown": {},
                    "min_confidence_threshold": 0.45,
                    "confidence_penalty": 0.05,
                    "aggression_multiplier": 0.8,
                    "position_size_multiplier": 0.7,
                    "leverage_cap": 10,
                }
            ),
        )
        request = engine.build_open_request({"action": "BUY", "reason": "x", "confidence": 0.9}, 100.0, market_context={"market_regime": "normal"})
        self.assertIsNotNone(request)
        self.assertLessEqual(request["leverage"], 10)
        self.assertLess(request["margin"], 200.0 * 0.42)

    def test_low_liquidity_failure_focus_blocks_high_slippage_context(self):
        engine = BaseFleetStrategyEngine(
            "BTC",
            _FakeExecutionEngine(),
            _FakePositionManager(),
            _FakeRiskEngine(),
            event_bus=None,
            learning_feedback=_FakeLearningFeedback(
                {
                    "symbol_cooldown": {},
                    "min_confidence_threshold": 0.35,
                    "confidence_penalty": 0.0,
                    "aggression_multiplier": 1.0,
                    "position_size_multiplier": 1.0,
                    "failure_focus_flags": ["low_liquidity"],
                }
            ),
        )
        request = engine.build_open_request(
            {"action": "BUY", "reason": "x", "confidence": 0.8},
            100.0,
            market_context={"market_regime": "high_slippage", "slippage_risk": "elevated"},
        )
        self.assertIsNone(request)
        self.assertEqual(engine.last_reason, "learning_low_liquidity_block")


if __name__ == "__main__":
    unittest.main()
