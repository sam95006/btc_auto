import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.autonomy.grid_signal_bridge import GridSignalBridge
from backend.governance.funding_arb_proposer import FundingArbProposer
from backend.risk.monthly_drawdown_guard import MonthlyDrawdownGuard
from backend.trading.grid_trading_engine import GridTradingEngine


class StrategyModulesTests(unittest.TestCase):
    def test_monthly_drawdown_blocks_at_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("backend.risk.monthly_drawdown_guard._state_path") as mock_path:
                state_file = Path(tmp) / "monthly_risk_state.json"
                mock_path.return_value = state_file
                guard = MonthlyDrawdownGuard()
                with patch("backend.risk.monthly_drawdown_guard.MONTHLY_MAX_DRAWDOWN_PCT", 0.10):
                    guard.evaluate(10000.0)
                    status = guard.evaluate(8900.0)
                self.assertTrue(status["breached"])
                self.assertTrue(status["block_new_entries"])
                self.assertEqual(status["block_reason"], "monthly_max_drawdown")

    def test_grid_engine_emits_buy_on_dip(self):
        engine = GridTradingEngine(lookback_ticks=12, spacing_pct=0.004, range_max_deviation_pct=0.02)
        history = [100.0] * 10 + [100.15, 99.15]
        signal = engine.evaluate(
            "BTCUSDT",
            99.2,
            history,
            market_context={"volatility_percentile": 0.4, "market_regime": "normal", "grid_max_vol": 0.72},
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal["side"], "BUY")

    def test_funding_proposer_long_on_negative_funding(self):
        proposer = FundingArbProposer()
        proposer._last_run = 0.0
        prices = {"BTC": {"symbol": "BTCUSDT", "price": 64000.0}}
        contexts = {
            "BTC": {
                "funding_rate": -0.0005,
                "liquidity_status": "healthy",
                "spread_status": "normal",
                "funding_risk": "normal",
            }
        }
        rows = proposer.collect_proposals(prices, market_contexts=contexts, positions=[], deployable_pool=500.0)
        self.assertTrue(rows)
        self.assertEqual(rows[0]["side"], "BUY")
        self.assertEqual(rows[0]["proposer"], "funding_arb")

    def test_grid_bridge_respects_interval(self):
        bridge = GridSignalBridge()
        bridge._last_run = 0.0
        prices = {"ETH": {"symbol": "ETHUSDT", "price": 3200.0}}
        first = bridge.collect_proposals(prices, market_contexts={"ETH": {"volatility_percentile": 0.4}}, deployable_pool=200.0)
        second = bridge.collect_proposals(prices, market_contexts={"ETH": {"volatility_percentile": 0.4}}, deployable_pool=200.0)
        self.assertEqual(second, [])


if __name__ == "__main__":
    unittest.main()
