import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from backend.learning.feedback_loop import LearningFeedbackLoop
from backend.learning.liquidation_tracker import LiquidationTracker
from backend.trading.radar_dispatch_service import RadarDispatchService
from backend.trading.trade_validation_pipeline import TradeValidationPipeline


class _MemoryStore:
    def __init__(self):
        self.trade_results = []
        self.patches = []

    def append_trade_result(self, result):
        self.trade_results.append(dict(result))

    def recent_trade_results(self, limit=200):
        return list(self.trade_results[-limit:])

    def append_signal_weight_recommendation(self, recommendation):
        return None

    def append_trade_validation_event(self, validation):
        return None

    def recent_trade_validation_events(self, limit=200):
        return []

    def applied_learning_for_fleet(self, fleet, strategy_key=None):
        return [patch for patch in self.patches if str(patch.get("fleet") or "").upper() == str(fleet).upper()]

    def upsert_applied_learning_patch(self, patch):
        self.patches.append(dict(patch))


class LiquidationLearningTests(unittest.TestCase):
    def test_liquidation_trade_records_and_blocks_symbol(self):
        store = _MemoryStore()
        feedback = LearningFeedbackLoop(store)
        recorded = []

        def record_fn(result, context=None):
            payload, recommendation = feedback.record_trade_result(result, context=context or {})
            recorded.append(payload)
            if recommendation:
                store.upsert_applied_learning_patch(
                    {
                        "fleet": recommendation.get("fleet"),
                        "strategy_key": recommendation.get("strategy_key"),
                        "blacklisted_symbol": recommendation.get("blacklist_candidate"),
                    }
                )
            return payload

        tracker = LiquidationTracker()
        tracker.reconcile(
            [],
            [
                {
                    "id": "live_trade_RADAR_99",
                    "fleet": "RADAR",
                    "symbol": "DOGEUSDT",
                    "side": "SELL",
                    "pnl": -17.92,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            ],
            MagicMock(is_configured=lambda: False),
            record_fn,
        )

        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["failure_reason"], "exchange_liquidation")
        guidance = feedback.get_strategy_guidance("RADAR", "radar_market_scan_strategy", "radar_alt")
        self.assertIn("DOGEUSDT", guidance.get("blocked_symbols", []))
        self.assertTrue(guidance["symbol_cooldown"]["DOGEUSDT"]["active"])

        pipeline = TradeValidationPipeline(store, feedback)
        validation = pipeline.evaluate(
            {
                "fleet": "RADAR",
                "symbol": "DOGEUSDT",
                "strategy_key": "radar_market_scan_strategy",
                "market_type": "futures",
            },
            market_context={"market_regime": "radar_alt"},
            truth_status={"futures_ready_for_ai": True},
        )
        self.assertFalse(validation["approved"])
        self.assertIn(
            validation["reason"],
            {"learning_liquidation_cooldown", "learning_symbol_blacklisted"},
        )

    def test_radar_dispatch_respects_learning_guidance(self):
        dispatch = RadarDispatchService()
        guidance = {
            "blocked_symbols": ["AGTUSDT"],
            "symbol_cooldown": {"UIUSDT": {"active": True, "reason": "exchange_liquidation"}},
            "pause_new_entries": False,
        }
        self.assertFalse(dispatch.can_open_symbol("AGTUSDT", learning_guidance=guidance))
        self.assertFalse(dispatch.can_open_symbol("UIUSDT", learning_guidance=guidance))
        self.assertTrue(dispatch.can_open_symbol("SOLUSDT", learning_guidance=guidance))


if __name__ == "__main__":
    unittest.main()
