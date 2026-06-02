import unittest

from backend.autonomy.pure_ai_hard_exit import merge_exit_actions_flexible
from backend.autonomy.pure_ai_position_policy import (
    apply_entry_throttle,
    filter_entries_by_learning,
    trend_confirms_position,
)


class PureAiPositionPolicyTests(unittest.TestCase):
    def test_learning_blocks_repeat_loss_side(self):
        proposals = [
            {"symbol": "XMRUSDT", "side": "SELL", "adjusted_confidence": 0.5},
            {"symbol": "BTCUSDT", "side": "BUY", "adjusted_confidence": 0.5},
        ]
        context = {
            "blocked_symbols": [],
            "symbol_lessons": {},
            "recent_pure_ai_losses": [{"symbol": "XMRUSDT", "side": "SELL", "pnl": -10}],
        }
        rows = filter_entries_by_learning(proposals, context)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "BTCUSDT")

    def test_entry_throttle_caps_new_and_pyramid(self):
        proposals = [
            {"symbol": "AUSDT", "side": "BUY"},
            {"symbol": "BUSDT", "side": "BUY"},
            {"symbol": "CUSDT", "side": "BUY"},
            {"symbol": "DUSDT", "side": "BUY", "pyramid_add": True},
            {"symbol": "EUSDT", "side": "BUY", "pyramid_add": True},
        ]
        rows = apply_entry_throttle(proposals, max_entries=2, max_pyramid=1)
        self.assertEqual(len(rows), 3)
        self.assertEqual(sum(1 for item in rows if item.get("pyramid_add")), 1)

    def test_trend_confirms_long_when_mark_above_entry(self):
        ok = trend_confirms_position(
            {"symbol": "BTCUSDT", "side": "BUY", "entry_price": 100.0, "mark_price": 101.0},
            {"core_fleets": {}, "market_context": {}},
        )
        self.assertTrue(ok)

    def test_flexible_merge_prefers_critical_hard_exit(self):
        hard = [
            {
                "symbol": "ETHUSDT",
                "action": "reduce_or_close",
                "fraction": 1.0,
                "urgency": "critical",
                "source": "pure_ai_hard_exit",
            }
        ]
        soft = [
            {
                "symbol": "ETHUSDT",
                "action": "take_partial_profit",
                "fraction": 0.5,
                "urgency": "medium",
                "source": "ai_flex_exit",
            }
        ]
        merged = merge_exit_actions_flexible(hard, soft)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["urgency"], "critical")


if __name__ == "__main__":
    unittest.main()
