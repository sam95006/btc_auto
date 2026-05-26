import unittest

from backend.analytics.monthly_revenue_tracker import MonthlyRevenueTracker
from backend.analytics.revenue_plan_service import RevenuePlanService
from backend.autonomy.rule_signal_bridge import RuleSignalBridge
from backend.learning.strategy_evolution_service import StrategyEvolutionService
from backend.monitoring.decision_funnel_service import DecisionFunnelService
from backend.monitoring.kill_switch_service import KillSwitchService


class P0P2RevenuePipelineTests(unittest.TestCase):
    def test_monthly_target_one_third_equity(self):
        report = MonthlyRevenueTracker().build_report(3470.0, trade_results=[])
        self.assertEqual(report["target_mode"], "third_of_futures_capital")
        self.assertAlmostEqual(report["target_usd"], round(3470.0 / 3.0, 1), places=0)

    def test_monthly_net_from_futures_closes(self):
        trades = [
            {
                "market_type": "futures",
                "event": "CLOSE",
                "pnl": 12.5,
                "commission": 0.5,
                "timestamp": report_month(),
            }
        ]
        report = MonthlyRevenueTracker().build_report(3000.0, trade_results=trades)
        self.assertGreaterEqual(report["realized_pnl_net"], 12.0)

    def test_revenue_plan_stages(self):
        monthly = {"target_usd": 1000, "realized_pnl_net": 50, "current_futures_equity": 3000}
        plan = RevenuePlanService().build_plan(monthly)
        self.assertEqual(plan["capital_scope"], "futures_only")
        self.assertGreaterEqual(len(plan["stages"]), 4)

    def test_funnel_diagnosis_when_empty(self):
        funnel = DecisionFunnelService().build_report()
        self.assertIn("管線", funnel.get("diagnosis", ""))

    def test_kill_switch_daily_loss(self):
        report = KillSwitchService().evaluate(growth_status={"daily_max_loss_hit": True})
        self.assertTrue(report.get("triggered"))
        self.assertTrue(report.get("should_pause"))

    def test_kill_switch_validation_choke_warn_only(self):
        events = [{"approved": False} for _ in range(80)]
        report = KillSwitchService().evaluate(validation_events=events)
        self.assertTrue(report.get("triggered"))
        self.assertFalse(report.get("should_pause"))
        self.assertEqual(report.get("action"), "warn_only")

    def test_kill_switch_sync_stale_warn_only_by_default(self):
        import time

        report = KillSwitchService().evaluate(
            live_sync={"updated_at_ms": int((time.time() - 600) * 1000)},
        )
        self.assertTrue(report.get("triggered"))
        self.assertFalse(report.get("should_pause"))

    def test_kill_switch_consecutive_losses_warn_only_by_default(self):
        from datetime import datetime

        trades = []
        for idx in range(6):
            trades.append(
                {
                    "market_type": "futures",
                    "event": "CLOSE",
                    "pnl": -2.0,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        report = KillSwitchService().evaluate(trade_results=trades)
        self.assertTrue(report.get("triggered"))
        self.assertFalse(report.get("should_pause"))
        self.assertIn("consecutive_losses", report.get("reasons") or [])

    def test_rotation_hold_under_revenue_growth(self):
        svc = StrategyEvolutionService()
        out = svc.evolve_growth_directives({}, rotation={"recommendation": "pause_rotation"}, recent_trades=[])
        self.assertEqual(out.get("evolution_mode"), "rotation_hold")

    def test_rule_bridge_proposals(self):
        bridge = RuleSignalBridge()
        bridge._last_run = 0.0
        prices = {"BTC": {"symbol": "BTCUSDT", "price": 100.0}}
        for i in range(12):
            prices["BTC"] = {"symbol": "BTCUSDT", "price": 100.0 + i * 0.08}
            proposals = bridge.collect_proposals(prices, deployable_pool=500.0)
        self.assertIsInstance(proposals, list)


def report_month():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    unittest.main()
