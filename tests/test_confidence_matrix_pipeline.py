import os
import unittest
from unittest.mock import patch

from backend.learning.dynamic_blocklist import DynamicBlocklist
from backend.risk.confidence_matrix_engine import ConfidenceMatrixEngine
from backend.risk.confidence_sizing_pipeline import ConfidenceSizingPipeline
from backend.risk.dynamic_asset_allocator import DynamicAssetAllocator


class ConfidenceMatrixPipelineTests(unittest.TestCase):
    def test_matrix_scores_bounded(self):
        engine = ConfidenceMatrixEngine()
        result = engine.score(
            {"fleet": "SOL", "side": "BUY", "symbol": "SOLUSDT"},
            market_context={
                "trend_bias": "bullish",
                "volume_confirmed": True,
                "rsi_14": 55,
                "funding_rate": -0.0001,
                "coingecko_liquidity_ok": True,
            },
            regime_state={"label": "TREND_BULL"},
        )
        self.assertGreaterEqual(result["confidence_score"], 40)
        self.assertLessEqual(result["confidence_score"], 100)

    @patch("backend.risk.dynamic_asset_allocator.HARD_MAX_LEVERAGE", 100.0)
    @patch("backend.risk.dynamic_asset_allocator.ABSOLUTE_MAX_LEVERAGE", 100.0)
    def test_allocator_tiers(self, *_mocks):
        alloc = DynamicAssetAllocator()
        low = alloc.allocate(65, fleet="RADAR", available_balance=1000)
        high = alloc.allocate(90, fleet="RADAR", available_balance=1000)
        self.assertLess(low["margin"], high["margin"])
        self.assertLess(low["leverage"], high["leverage"])

    @patch("backend.risk.dynamic_asset_allocator.HARD_MAX_LEVERAGE", 100.0)
    @patch("backend.risk.dynamic_asset_allocator.ABSOLUTE_MAX_LEVERAGE", 100.0)
    def test_allocator_confidence_table_btc_100x(self, *_mocks):
        alloc = DynamicAssetAllocator()
        result = alloc.allocate(95, fleet="BTC", available_balance=10000)
        self.assertEqual(result["leverage_mode"], "confidence_table")
        self.assertGreaterEqual(result["leverage"], 50)
        self.assertLessEqual(result["leverage"], 100)

    def test_pipeline_applies_matrix(self):
        blocklist = DynamicBlocklist()
        pipeline = ConfidenceSizingPipeline(blocklist=blocklist)
        proposal = {
            "fleet": "RADAR",
            "symbol": "DOGEUSDT",
            "side": "BUY",
            "decision_source": "llm_proposer",
            "strategy_key": "ai_led_trade_proposer",
        }
        out = pipeline.apply(
            proposal,
            market_context={"trend_bias": "bullish", "funding_rate": 0.0001},
            regime_state={"label": "TREND_BULL"},
            deployable_pool=500,
            available_balance=2000,
        )
        self.assertTrue(out.get("confidence_matrix_applied"))
        self.assertIn("confidence_matrix", out)


if __name__ == "__main__":
    unittest.main()
