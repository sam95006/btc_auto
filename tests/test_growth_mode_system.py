import shutil
import tempfile
import unittest
from pathlib import Path

from backend.analytics.daily_pnl_tracker import DailyPnlTracker
from backend.risk.capital_growth_guard import CapitalGrowthGuard
from backend.decision.meeting_notes_resolver import resolve_meeting_notes
from backend.trading.decision_quality_engine import DecisionQualityValidationEngine
from backend.analytics.walk_forward_evaluator import WalkForwardEvaluator


class CapitalGrowthGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="nexus_growth_guard_"))
        tracker = DailyPnlTracker(state_path=self.temp_dir / "daily.json")
        self.guard = CapitalGrowthGuard(daily_tracker=tracker)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_recovery_mode_below_floor(self):
        status = self.guard.evaluate(9600.0)
        self.assertEqual(status["mode"], "RECOVERY")
        self.assertFalse(status["above_floor"])
        self.assertLessEqual(status["max_leverage"], 12.0)

    def test_growth_mode_above_floor(self):
        status = self.guard.evaluate(12500.0)
        self.assertIn(status["mode"], {"GROWTH", "DAILY_DEFENSE", "FLOOR_GUARD"})
        self.assertTrue(status["above_floor"])

    def test_daily_loss_blocks_entries(self):
        tracker = self.guard.daily_tracker
        tracker._day = tracker._day or "2026-05-19"
        tracker._start_equity = 12000.0
        status = self.guard.evaluate(11800.0)
        self.assertTrue(status["block_new_entries"])
        self.assertEqual(status["block_reason"], "daily_loss_limit_reached")


class MeetingNotesResolverTests(unittest.TestCase):
    def test_resolve_from_meeting_conclusion(self):
        notes = resolve_meeting_notes(
            [
                {
                    "meeting_id": "scheduled_2026-05-19_06-00",
                    "conclusion": {
                        "risk_notes": {"RISK": ["高波動階段需保守"]},
                        "forbidden_actions": {"PEPE": ["禁止加槓桿"]},
                        "next_6h_focus": ["觀察低量反彈"],
                    },
                }
            ]
        )
        self.assertTrue(notes["forbidden_actions_map"].get("PEPE"))
        self.assertTrue(any("高波" in item for item in notes["risk_notes"]))


class DecisionQualityEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = DecisionQualityValidationEngine()

    def test_blocks_when_growth_guard_blocks(self):
        result = self.engine.evaluate(
            {"fleet": "BTC", "side": "BUY", "adjusted_confidence": 0.8},
            market_context={"market_regime": "normal", "volume_confirmed": True},
            growth_context={"growth_directives": {"block_new_entries": True, "block_reason": "daily_loss_limit_reached"}},
        )
        self.assertFalse(result["approved"])
        self.assertEqual(result["reason"], "daily_loss_limit_reached")

    def test_passes_high_quality_setup(self):
        result = self.engine.evaluate(
            {"fleet": "BTC", "side": "BUY", "adjusted_confidence": 0.84, "strategy_key": "btc_adaptive_strategy"},
            market_context={
                "market_regime": "normal",
                "volume_confirmed": True,
                "trend_strength": 0.02,
                "support_distance": 0.01,
                "volatility_percentile": 0.4,
            },
            growth_context={
                "signal": {"action": "BUY", "confidence": 0.84, "reason": "pullback"},
                "growth_directives": {"min_quality_score": 0.65},
                "capital_snapshot": {"fleets": {"BTC": {"realized_pnl": 0.0}}},
            },
        )
        self.assertTrue(result["approved"])
        self.assertGreater(result["quality_score"], 0.65)


class WalkForwardEvaluatorTests(unittest.TestCase):
    def test_not_ready_with_small_sample(self):
        result = WalkForwardEvaluator(window_size=10).evaluate([{"pnl": 1.0}] * 5)
        self.assertFalse(result["ready"])

    def test_ready_with_enough_sample(self):
        rows = [{"pnl": 2.0 if idx % 2 == 0 else -1.0} for idx in range(20)]
        result = WalkForwardEvaluator(window_size=10, step_size=5).evaluate(rows)
        self.assertTrue(result["ready"])
        self.assertGreater(result["window_count"], 0)


if __name__ == "__main__":
    unittest.main()
