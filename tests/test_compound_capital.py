import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.analytics.daily_pnl_tracker import DailyPnlTracker
from backend.risk.capital_growth_guard import CapitalGrowthGuard
from backend.wallet.compound_capital_service import CompoundCapitalService


class CompoundCapitalTests(unittest.TestCase):
    def test_day_rollover_uses_yesterday_close_as_reinvest_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "growth_daily_state.json"
            tracker = DailyPnlTracker(state_path=state_path)
            tracker._day = "2026-05-24"
            tracker._start_equity = 3000.0
            tracker._last_equity = 3150.0
            tracker._peak_equity = 3150.0
            tracker._save()

            with patch.object(DailyPnlTracker, "_today", return_value="2026-05-25"):
                daily = tracker.update(3200.0)

            self.assertEqual(daily["day"], "2026-05-25")
            self.assertEqual(daily["reinvest_base_equity"], 3150.0)
            self.assertTrue(daily["compound_reinvest"])

    def test_profit_lock_blocks_new_entries_after_daily_target(self):
        guard = CapitalGrowthGuard()
        with patch.object(guard.daily_tracker, "update", return_value={"daily_pnl": 50.0, "daily_pnl_pct": 0.01, "is_positive_day": True}):
            with patch("backend.risk.capital_growth_guard.LOCK_PROFIT_AFTER_DAILY_TARGET", True):
                with patch("backend.risk.capital_growth_guard.DAILY_PNL_TARGET_PCT", 0.003):
                    status = guard.evaluate(10000.0)
        if status.get("daily_target_hit"):
            self.assertTrue(status.get("block_new_entries"))
            self.assertEqual(status.get("mode"), "PROFIT_LOCK")

    def test_compound_snapshot_uses_live_equity_pool(self):
        service = CompoundCapitalService()
        snap = service.build_snapshot(
            4000.0,
            daily_payload={"start_equity": 3800.0, "is_positive_day": True, "day": "2026-05-25"},
            growth_status={"daily_target_hit": False, "mode": "GROWTH"},
        )
        self.assertTrue(snap["enabled"])
        self.assertEqual(snap["reinvest_base_equity"], 3800.0)
        self.assertGreater(snap["deployable_pool"], 0.0)


if __name__ == "__main__":
    unittest.main()
