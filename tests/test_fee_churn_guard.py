import os
import unittest
from unittest.mock import patch

from backend.trading.fee_churn_guard import FeeChurnGuard, estimate_round_trip_fee_usd


class FeeChurnGuardTests(unittest.TestCase):
    def setUp(self):
        self.guard = FeeChurnGuard()

    def test_round_trip_fee_estimate(self):
        fee = estimate_round_trip_fee_usd(50, 10)
        self.assertGreater(fee, 0.3)

    def test_blocks_small_margin(self):
        with patch.dict(os.environ, {"NEXUS_FEE_CHURN_GUARD": "1", "NEXUS_MIN_MARGIN_USD": "45"}, clear=False):
            ok, reason = self.guard.allow_open({"symbol": "BTCUSDT", "margin": 20, "leverage": 10, "adjusted_confidence": 0.6})
            self.assertFalse(ok)
            self.assertEqual(reason, "fee_churn_margin_too_small")

    def test_blocks_reopen_cooldown(self):
        self.guard.mark_symbol_closed("SOLUSDT")
        ok, reason = self.guard.allow_open(
            {"symbol": "SOLUSDT", "margin": 50, "leverage": 10, "adjusted_confidence": 0.7}
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "fee_churn_symbol_reopen_cooldown")

    def test_blocks_ai_exit_before_min_hold(self):
        ok, reason = self.guard.allow_ai_exit(
            {"opened_at": "2099-01-01 00:00:00", "unrealized_pnl": -0.2, "margin": 50},
            {"reason": "liquidation_pressure", "market_context": {"liquidation_risk": "critical"}},
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "fee_churn_min_hold_not_met")

    def test_blocks_partial_profit_below_fees(self):
        ok, reason = self.guard.allow_r_partial(
            {"id": "pos1", "opened_at": "2000-01-01 00:00:00", "margin": 30, "leverage": 8},
            0.12,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "fee_churn_partial_profit_below_fees")


if __name__ == "__main__":
    unittest.main()
