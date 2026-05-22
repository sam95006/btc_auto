import unittest

from backend.trading.exchange_capital_view import (
    build_ui_capital,
    futures_equity_from_account,
    treasury_totals_from_balances,
)


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

    def test_treasury_ignores_btc_holdings_in_balances(self):
        spot = {
            "balances": {
                "USDT": {"free": 5000.0, "locked": 0.0},
                "USDC": {"free": 5000.0, "locked": 0.0},
                "BTC": {"free": 1.0, "locked": 0.0},
            },
            "usdt_total": 99999.0,
            "spot_stable_total": 99999.0,
            "holdings_total": 60000.0,
        }
        capital = build_ui_capital(spot, {})
        self.assertEqual(capital["spot_usdt_total"], 5000.0)
        self.assertEqual(capital["spot_usdc_total"], 5000.0)
        self.assertEqual(capital["spot_stable_total"], 10000.0)
        self.assertEqual(capital["total"], 10000.0)

    def test_treasury_totals_from_balances_helper(self):
        usdt, usdc, total = treasury_totals_from_balances(
            {"USDT": {"free": 1, "locked": 2}, "USDC": {"free": 3, "locked": 0}, "ETH": {"free": 9, "locked": 0}}
        )
        self.assertEqual((usdt, usdc, total), (3.0, 3.0, 6.0))

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
