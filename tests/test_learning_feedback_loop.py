import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from backend.learning.feedback_loop import LearningFeedbackLoop
from backend.services.runtime_store import RuntimeStateStore


class LearningFeedbackLoopTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="nexus_learning_"))
        self.store = RuntimeStateStore(str(self.temp_dir / "learning.db"))
        self.loop = LearningFeedbackLoop(self.store)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_trade_journal_can_be_written(self):
        self.loop.record_trade_journal(
            {
                "timestamp": "2026-05-11 10:00:00",
                "symbol": "BTCUSDT",
                "market_type": "futures",
                "fleet": "BTC",
            }
        )
        items = self.store.recent_trade_journal(limit=10)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["symbol"], "BTCUSDT")

    def test_trade_result_loss_generates_failure_reason_and_recommendation(self):
        payload, recommendation = self.loop.record_trade_result(
            {
                "timestamp": "2026-05-11 10:05:00",
                "order_id": "ord-1",
                "symbol": "BTCUSDT",
                "market_type": "futures",
                "fleet": "BTC",
                "entry_price": 100.0,
                "exit_price": 90.0,
                "pnl": -10.0,
                "final_leverage": 50,
            },
            context={
                "confidence_score": 0.9,
                "market_regime": "normal",
                "strategy_key": "breakout",
            },
        )
        self.assertEqual(payload["win_loss"], "LOSS")
        self.assertIn(payload["failure_reason"], {"confidence_overestimated", "over_leverage"})
        self.assertIsNotNone(recommendation)
        recs = self.store.recent_signal_weight_recommendations(limit=10)
        self.assertGreaterEqual(len(recs), 1)

    def test_calibration_snapshot_penalizes_repeated_high_leverage_losses(self):
        for idx in range(3):
            self.loop.record_trade_result(
                {
                    "timestamp": f"2026-05-11 10:0{idx}:00",
                    "order_id": f"ord-{idx}",
                    "symbol": "BTCUSDT",
                    "market_type": "futures",
                    "fleet": "BTC",
                    "strategy_key": "btc_adaptive_strategy",
                    "entry_price": 100.0,
                    "exit_price": 90.0,
                    "pnl": -10.0,
                    "final_leverage": 50,
                    "confidence_score": 0.91,
                    "market_regime": "normal",
                },
                context={
                    "confidence_score": 0.91,
                    "market_regime": "normal",
                    "strategy_key": "btc_adaptive_strategy",
                },
            )

        guidance = self.loop.get_strategy_guidance("BTC", "btc_adaptive_strategy", "normal")
        self.assertGreater(guidance["confidence_penalty"], 0.0)
        self.assertIn(guidance["leverage_cap"], {3, 10, 20})

    def test_blocked_regime_emerges_from_repeated_regime_losses(self):
        for idx in range(3):
            self.loop.record_trade_result(
                {
                    "timestamp": f"2026-05-11 11:0{idx}:00",
                    "order_id": f"sol-{idx}",
                    "symbol": "SOLUSDT",
                    "market_type": "futures",
                    "fleet": "SOL",
                    "strategy_key": "sol_adaptive_strategy",
                    "entry_price": 100.0,
                    "exit_price": 95.0,
                    "pnl": -5.0,
                    "final_leverage": 10,
                    "confidence_score": 0.77,
                    "market_regime": "thin_liquidity",
                    "failure_reason": "low_liquidity",
                },
                context={
                    "confidence_score": 0.77,
                    "market_regime": "thin_liquidity",
                    "strategy_key": "sol_adaptive_strategy",
                    "liquidity_risk": True,
                },
            )

        guidance = self.loop.get_strategy_guidance("SOL", "sol_adaptive_strategy", "thin_liquidity")
        self.assertTrue(guidance["regime_blocked"])

    def test_symbol_cooldown_appears_after_repeated_symbol_losses(self):
        base = datetime.now()
        for idx in range(3):
            self.loop.record_trade_result(
                {
                    "timestamp": (base - timedelta(minutes=idx)).strftime("%Y-%m-%d %H:%M:%S"),
                    "order_id": f"btc-loss-{idx}",
                    "symbol": "BTCUSDT",
                    "market_type": "futures",
                    "fleet": "BTC",
                    "strategy_key": "btc_adaptive_strategy",
                    "pnl": -8.0,
                    "win_loss": "LOSS",
                    "final_leverage": 10,
                },
                context={
                    "strategy_key": "btc_adaptive_strategy",
                    "market_regime": "normal",
                },
            )

        guidance = self.loop.get_strategy_guidance("BTC", "btc_adaptive_strategy", "normal")
        self.assertIn("BTCUSDT", guidance["symbol_cooldown"])
        self.assertTrue(guidance["symbol_cooldown"]["BTCUSDT"]["active"])
        self.assertGreaterEqual(guidance["min_confidence_threshold"], 0.35)

    def test_high_slippage_loss_is_classified_as_low_liquidity(self):
        payload, _recommendation = self.loop.record_trade_result(
            {
                "timestamp": "2026-05-18 10:20:00",
                "order_id": "ord-slip",
                "symbol": "ETHUSDT",
                "market_type": "futures",
                "fleet": "ETH",
                "strategy_key": "eth_adaptive_strategy",
                "pnl": -4.2,
                "final_leverage": 10,
            },
            context={
                "strategy_key": "eth_adaptive_strategy",
                "market_regime": "high_slippage",
                "slippage_risk": "elevated",
            },
        )
        self.assertEqual(payload["failure_reason"], "low_liquidity")

    def test_funding_dislocation_loss_is_classified_as_bad_market_regime(self):
        payload, _recommendation = self.loop.record_trade_result(
            {
                "timestamp": "2026-05-18 10:25:00",
                "order_id": "ord-funding",
                "symbol": "SOLUSDT",
                "market_type": "futures",
                "fleet": "SOL",
                "strategy_key": "sol_adaptive_strategy",
                "pnl": -3.8,
                "final_leverage": 8,
            },
            context={
                "strategy_key": "sol_adaptive_strategy",
                "market_regime": "funding_dislocation",
                "funding_risk": "elevated",
            },
        )
        self.assertEqual(payload["failure_reason"], "bad_market_regime")

    def test_strategy_guidance_includes_adaptive_mode_and_overrides(self):
        for idx in range(3):
            self.loop.record_trade_result(
                {
                    "timestamp": f"2026-05-18 11:0{idx}:00",
                    "order_id": f"eth-loss-{idx}",
                    "symbol": "ETHUSDT",
                    "market_type": "futures",
                    "fleet": "ETH",
                    "strategy_key": "eth_adaptive_strategy",
                    "pnl": -5.0,
                    "final_leverage": 20,
                    "market_regime": "basis_dislocation",
                },
                context={
                    "strategy_key": "eth_adaptive_strategy",
                    "market_regime": "basis_dislocation",
                    "basis_risk": "elevated",
                },
            )

        guidance = self.loop.get_strategy_guidance(
            "ETH",
            "eth_adaptive_strategy",
            "basis_dislocation",
            market_context={"market_regime": "basis_dislocation", "basis_risk": "elevated"},
        )
        self.assertIn(guidance["adaptive_mode"], {"restricted", "suspended"})
        self.assertIn("strategy_adaptation", guidance)
        self.assertGreaterEqual(
            guidance["strategy_adaptation"]["overrides"]["min_confidence_threshold"],
            guidance["min_confidence_threshold"],
        )



if __name__ == "__main__":
    unittest.main()
