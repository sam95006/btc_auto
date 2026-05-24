import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from backend.services.runtime_store import RuntimeStateStore
from backend.learning.feedback_loop import LearningFeedbackLoop
from backend.trading.trade_validation_pipeline import TradeValidationPipeline


class TradeValidationPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="nexus_validation_pipeline_"))
        self.store = RuntimeStateStore(str(self.temp_dir / "validation.db"))
        self.learning = LearningFeedbackLoop(self.store)
        self.pipeline = TradeValidationPipeline(self.store, learning_feedback=self.learning)
        self.base_proposal = {
            "timestamp": "2026-05-15 18:00:00",
            "fleet": "BTC",
            "symbol": "BTCUSDT",
            "market_type": "futures",
            "strategy_key": "btc_adaptive_strategy",
            "side": "SELL",
            "margin": 25.0,
            "adjusted_confidence": 0.82,
            "raw_confidence": 0.82,
        }
        self.healthy_context = {
            "market_regime": "normal",
            "spread_bps": 2.5,
            "top5_cross_notional": 250000.0,
            "liquidity_status": "healthy",
            "volume_confirmed": True,
            "trend_strength": -0.02,
            "resistance_distance": 0.01,
            "volatility_percentile": 0.35,
        }
        self.healthy_truth = {"fresh_for_ai": True}
        self.growth_context = {
            "signal": {"action": "SELL", "confidence": 0.82, "reason": "test_signal"},
            "growth_directives": {"min_quality_score": 0.65, "min_approval_score": 0.52, "min_win_rate": 0.35},
            "capital_snapshot": {"fleets": {"BTC": {"realized_pnl": 0.0}}},
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _record_loss(self, idx, pnl=-5.0):
        self.store.append_trade_result(
            {
                "timestamp": f"2026-05-15 17:0{idx}:00",
                "order_id": f"ord-{idx}",
                "symbol": "BTCUSDT",
                "market_type": "futures",
                "fleet": "BTC",
                "strategy_key": "btc_adaptive_strategy",
                "pnl": pnl,
                "win_loss": "LOSS" if pnl < 0 else "WIN",
            }
        )

    def test_bootstrap_history_can_pass(self):
        result = self.pipeline.evaluate(
            self.base_proposal,
            market_context=self.healthy_context,
            truth_status=self.healthy_truth,
            recent_orders=[],
            recent_trades=[],
            growth_context=self.growth_context,
        )
        self.assertTrue(result["approved"])
        self.assertEqual(result["stages"]["backtest"]["reason"], "no_history_bootstrap_allowed")

    def test_backtest_blocks_weak_history(self):
        for idx in range(6):
            self._record_loss(idx, pnl=-6.0)
        result = self.pipeline.evaluate(
            self.base_proposal,
            market_context=self.healthy_context,
            truth_status=self.healthy_truth,
            recent_orders=[],
            recent_trades=[],
            growth_context=self.growth_context,
        )
        self.assertFalse(result["approved"])
        self.assertEqual(result["stages"]["backtest"]["reason"], "historical_edge_too_weak")

    def test_simulation_blocks_stale_truth(self):
        result = self.pipeline.evaluate(
            self.base_proposal,
            market_context=self.healthy_context,
            truth_status={"fresh_for_ai": False},
            recent_orders=[],
            recent_trades=[],
            growth_context=self.growth_context,
        )
        self.assertFalse(result["approved"])
        self.assertEqual(result["stages"]["simulation"]["reason"], "truth_layer_not_fresh")

    def test_paper_trade_blocks_repeat_validation_failures(self):
        for idx in range(4):
            self.store.append_trade_validation_event(
                {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "fleet": "BTC",
                    "symbol": "BTCUSDT",
                    "approved": False,
                    "reason": "insufficient_liquidity",
                }
            )
        result = self.pipeline.evaluate(
            self.base_proposal,
            market_context=self.healthy_context,
            truth_status=self.healthy_truth,
            recent_orders=[],
            recent_trades=[],
            growth_context=self.growth_context,
        )
        self.assertFalse(result["approved"])
        self.assertEqual(result["stages"]["paper_trade"]["reason"], "recent_validation_blocks_too_many")

    def test_status_snapshot_reports_counts(self):
        self.pipeline.evaluate(
            self.base_proposal,
            market_context=self.healthy_context,
            truth_status=self.healthy_truth,
            recent_orders=[],
            recent_trades=[],
            growth_context=self.growth_context,
        )
        status = self.pipeline.build_status_snapshot(limit=20)
        self.assertEqual(status["event_count"], 1)
        self.assertIn("BTC", status["by_fleet"])

    def test_simulation_blocks_high_slippage(self):
        result = self.pipeline.evaluate(
            self.base_proposal,
            market_context={**self.healthy_context, "worst_slippage_bps": 12.0},
            truth_status=self.healthy_truth,
            recent_orders=[],
            recent_trades=[],
            growth_context=self.growth_context,
        )
        self.assertFalse(result["approved"])
        self.assertEqual(result["stages"]["simulation"]["reason"], "slippage_too_high")

    def test_simulation_blocks_liquidation_pressure(self):
        result = self.pipeline.evaluate(
            self.base_proposal,
            market_context={**self.healthy_context, "liquidation_risk": "critical", "liquidation_distance_pct": 0.02},
            truth_status=self.healthy_truth,
            recent_orders=[],
            recent_trades=[],
            growth_context=self.growth_context,
        )
        self.assertFalse(result["approved"])
        self.assertEqual(result["stages"]["simulation"]["reason"], "liquidation_pressure_too_high")

    def test_learning_guidance_can_block_symbol_after_repeated_losses(self):
        import os

        os.environ["NEXUS_BOLD_TESTNET"] = "0"
        base = datetime.now()
        for idx in range(3):
            self.learning.record_trade_result(
                {
                    "timestamp": (base - timedelta(minutes=idx)).strftime("%Y-%m-%d %H:%M:%S"),
                    "order_id": f"loss-{idx}",
                    "symbol": "BTCUSDT",
                    "market_type": "futures",
                    "fleet": "BTC",
                    "strategy_key": "btc_adaptive_strategy",
                    "pnl": -6.0,
                    "final_leverage": 10,
                },
                context={"strategy_key": "btc_adaptive_strategy", "market_regime": "normal"},
            )
        result = self.pipeline.evaluate(
            self.base_proposal,
            market_context=self.healthy_context,
            truth_status=self.healthy_truth,
            recent_orders=[],
            recent_trades=[],
            growth_context=self.growth_context,
        )
        self.assertFalse(result["approved"])
        self.assertEqual(result["reason"], "learning_symbol_cooldown")
        self.assertIn("learning_guidance", result)
        os.environ["NEXUS_BOLD_TESTNET"] = "1"

    def test_portfolio_blocks_same_side_concentration(self):
        import os

        os.environ["NEXUS_BOLD_TESTNET"] = "0"
        portfolio_status = {
            "fleet_restrictions": {
                "BTC": {
                    "allowed_new_entries": True,
                    "capital_multiplier": 1.0,
                    "leverage_cap": None,
                }
            },
            "fleet_exposures": {"BTC": {"notional": 500.0}},
            "same_side_concentration": 0.82,
            "correlation_concentration": 0.40,
            "reserve_action": "hold",
            "notional_utilization": 0.55,
            "hedge_recommendations": [],
        }
        result = self.pipeline.evaluate(
            self.base_proposal,
            market_context=self.healthy_context,
            truth_status=self.healthy_truth,
            recent_orders=[],
            recent_trades=[],
            portfolio_status=portfolio_status,
            growth_context=self.growth_context,
        )
        self.assertFalse(result["approved"])
        self.assertEqual(result["stages"]["portfolio"]["reason"], "same_side_concentration_too_high")
        self.assertEqual(result["reason"], "same_side_concentration_too_high")
        os.environ["NEXUS_BOLD_TESTNET"] = "1"

    def test_portfolio_blocks_when_reserve_increase_and_utilization_full(self):
        import os

        os.environ["NEXUS_BOLD_TESTNET"] = "0"
        portfolio_status = {
            "fleet_restrictions": {
                "BTC": {
                    "allowed_new_entries": True,
                    "capital_multiplier": 0.8,
                    "leverage_cap": 10,
                }
            },
            "fleet_exposures": {"BTC": {"notional": 500.0}},
            "same_side_concentration": 0.50,
            "correlation_concentration": 0.35,
            "reserve_action": "increase_reserve",
            "notional_utilization": 1.02,
            "hedge_recommendations": ["reduce_same_side_concentration"],
        }
        result = self.pipeline.evaluate(
            self.base_proposal,
            market_context=self.healthy_context,
            truth_status=self.healthy_truth,
            recent_orders=[],
            recent_trades=[],
            portfolio_status=portfolio_status,
            growth_context=self.growth_context,
        )
        self.assertFalse(result["approved"])
        self.assertEqual(result["stages"]["portfolio"]["reason"], "portfolio_reserve_increase_block")
        self.assertEqual(result["reason"], "portfolio_reserve_increase_block")
        os.environ["NEXUS_BOLD_TESTNET"] = "1"

    def test_bold_testnet_allows_new_fleet_when_book_is_same_side_heavy(self):
        import os

        os.environ["NEXUS_BOLD_TESTNET"] = "1"
        portfolio_status = {
            "fleet_restrictions": {
                "SOL": {"allowed_new_entries": True},
            },
            "fleet_exposures": {
                "ETH": {"notional": 500.0},
                "RADAR": {"notional": 100.0},
            },
            "same_side_concentration": 0.95,
            "correlation_concentration": 0.70,
            "reserve_action": "increase_reserve",
            "notional_utilization": 1.05,
            "hedge_recommendations": [],
        }
        proposal = {**self.base_proposal, "fleet": "SOL", "symbol": "SOLUSDT"}
        result = self.pipeline.evaluate(
            proposal,
            market_context=self.healthy_context,
            truth_status=self.healthy_truth,
            recent_orders=[],
            recent_trades=[],
            portfolio_status=portfolio_status,
            growth_context=self.growth_context,
        )
        self.assertTrue(result["approved"])
        self.assertEqual(result["stages"]["portfolio"]["reason"], "bold_testnet_fleet_diversification_allowed")


if __name__ == "__main__":
    unittest.main()
