import unittest

from backend.learning.strategy_evolution_service import StrategyEvolutionService
from backend.trading.trade_validation_pipeline import _quality_gate_block, _symbol_lesson_gate


class StrategyEvolutionQualityTests(unittest.TestCase):
    def test_evolution_tightens_on_weak_walk_forward(self):
        service = StrategyEvolutionService()
        out = service.evolve_growth_directives(
            {"position_multiplier": 1.0},
            walk_forward_status={"ready": True, "positive_window_ratio": 0.2, "latest_window": {"win_rate": 0.3}},
            rotation={"recommendation": "tighten_guards"},
            recent_trades=[{"pnl": -1}] * 12,
        )
        self.assertTrue(out.get("strategy_evolution_applied"))
        self.assertLessEqual(float(out.get("position_multiplier", 1)), 0.82)

    def test_symbol_lesson_blocks_low_confidence(self):
        blocked, reason = _symbol_lesson_gate(
            "DOGEUSDT",
            {"confidence_score": 0.5},
            {"symbol_lessons": {"DOGEUSDT": {"min_confidence": 0.72}}},
        )
        self.assertTrue(blocked)
        self.assertEqual(reason, "learning_symbol_lesson_low_confidence")

    def test_quality_gate_requires_confidence(self):
        blocked, reason = _quality_gate_block(
            {"confidence_score": 0.4},
            {"min_trade_confidence": 0.68},
            [{"pnl": -1, "event": "CLOSE"}] * 10,
        )
        self.assertTrue(blocked)
        self.assertIn("quality_gate", reason)


if __name__ == "__main__":
    unittest.main()
