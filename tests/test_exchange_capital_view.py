import unittest

from backend.trading.exchange_capital_view import build_ui_capital, futures_equity_from_account


class ExchangeCapitalViewTests(unittest.TestCase):
    def test_ui_capital_uses_only_binance_summary_fields(self):
        spot = {
            "usdt_total": 5000.0,
            "usdc_total": 5000.0,
            "spot_stable_total": 10000.0,
            "stable_free": 10000.0,
            "update_time": 1,
            "sync_status": "ok",
        }
        futures = {
            "exchange_account": {
                "totalWalletBalance": 9332.0,
                "totalMarginBalance": 9323.0,
                "totalUnrealizedProfit": -9.67,
                "availableBalance": 8000.0,
            },
            "exchange_wallet_balance": 9332.0,
            "exchange_margin_balance": 9323.0,
            "unrealized_pnl": -9.67,
            "update_time": 2,
            "sync_status": "ok",
        }
        capital = build_ui_capital(spot, futures)
        self.assertEqual(capital["source"], "binance_rest")
        self.assertEqual(capital["spot_usdt_total"], 5000.0)
        self.assertEqual(capital["spot_usdc_total"], 5000.0)
        self.assertEqual(capital["futures_total"], 9323.0)
        self.assertEqual(capital["futures_wallet_display"], 9332.0)
        self.assertEqual(capital["total"], 19323.0)
        self.assertEqual(capital["futures_unrealized_pnl"], -9.67)

    def test_futures_equity_prefers_exchange_margin_balance(self):
        equity = futures_equity_from_account(
            {
                "margin_total": 100.0,
                "exchange_account": {"totalMarginBalance": 9323.0},
            }
        )
        self.assertEqual(equity, 9323.0)


if __name__ == "__main__":
    unittest.main()
