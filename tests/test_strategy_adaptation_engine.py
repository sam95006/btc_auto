import unittest

from backend.learning.strategy_adaptation_engine import StrategyAdaptationEngine


class StrategyAdaptationEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = StrategyAdaptationEngine()

    def test_cautious_mode_when_market_pressure_rises(self):
        adaptation = self.engine.evaluate(
            "BTC",
            "btc_adaptive_strategy",
            base_guidance={
                "loss_rate": 0.3,
                "consecutive_losses": 1,
                "confidence_penalty": 0.02,
                "aggression_multiplier": 1.0,
                "position_size_multiplier": 1.0,
                "min_confidence_threshold": 0.35,
                "blocked_regimes": [],
            },
            market_context={
                "market_regime": "high_slippage",
                "slippage_risk": "elevated",
                "liquidity_status": "thin",
                "oi_notional_status": "weak",
            },
        )
        self.assertEqual(adaptation["mode"], "cautious")
        self.assertIn("tighten_entry_filter", adaptation["recommended_actions"])

    def test_restricted_mode_blocks_bad_regime(self):
        adaptation = self.engine.evaluate(
            "SOL",
            "sol_adaptive_strategy",
            base_guidance={
                "loss_rate": 0.62,
                "consecutive_losses": 3,
                "confidence_penalty": 0.14,
                "aggression_multiplier": 1.0,
                "position_size_multiplier": 1.0,
                "min_confidence_threshold": 0.35,
                "blocked_regimes": [],
                "failure_focus": ["bad_market_regime"],
            },
            market_context={
                "market_regime": "basis_dislocation",
                "basis_risk": "elevated",
                "funding_risk": "normal",
            },
        )
        self.assertEqual(adaptation["mode"], "restricted")
        self.assertIn("basis_dislocation", adaptation["overrides"]["blocked_regimes"])
        self.assertTrue(adaptation["review_required"])

    def test_suspended_mode_for_hard_loss_streak(self):
        adaptation = self.engine.evaluate(
            "PEPE",
            "pepe_adaptive_strategy",
            base_guidance={
                "loss_rate": 0.8,
                "consecutive_losses": 5,
                "confidence_penalty": 0.2,
                "aggression_multiplier": 1.0,
                "position_size_multiplier": 1.0,
                "min_confidence_threshold": 0.35,
                "blocked_regimes": [],
                "pause_new_entries": True,
                "failure_focus": ["over_leverage"],
            },
            market_context={
                "market_regime": "normal",
                "slippage_risk": "normal",
            },
        )
        self.assertEqual(adaptation["mode"], "suspended")
        self.assertTrue(adaptation["pause_new_entries"])
        self.assertEqual(adaptation["overrides"]["leverage_cap"], 3)


if __name__ == "__main__":
    unittest.main()
