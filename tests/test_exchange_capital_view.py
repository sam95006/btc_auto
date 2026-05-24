import os
import unittest
from importlib import reload


def _reload_capital_modules(treasury_env: str | None):
    if treasury_env is None:
        os.environ.pop("NEXUS_TREASURY_ASSETS", None)
    else:
        os.environ["NEXUS_TREASURY_ASSETS"] = treasury_env
    import config.capital_display_config as capital_cfg
    import backend.trading.exchange_capital_view as view

    reload(capital_cfg)
    reload(view)
    return view


class ExchangeCapitalViewTests(unittest.TestCase):
    def test_usdt_only_futures_uses_asset_row_not_account_total(self):
        view = _reload_capital_modules("USDT")
        try:
            spot = {"balances": {"USDT": {"free": 1000.0, "locked": 0.0}}, "update_time": 1, "sync_status": "ok"}
            futures = {
                "exchange_account": {"totalWalletBalance": 9257.0, "totalMarginBalance": 9257.0},
                "balance_assets": [
                    {
                        "asset": "USDC",
                        "balance": 5000.0,
                        "cross_wallet_balance": 5000.0,
                        "cross_unrealized_pnl": 0.0,
                        "available_balance": 5000.0,
                    },
                    {
                        "asset": "USDT",
                        "balance": 3488.7164,
                        "cross_wallet_balance": 3488.7164,
                        "cross_unrealized_pnl": -2.65,
                        "available_balance": 2970.51,
                    },
                ],
                "update_time": 2,
                "sync_status": "ok",
            }
            capital = view.build_ui_capital(spot, futures)
            self.assertEqual(capital["treasury_assets"], ["USDT"])
            self.assertEqual(capital["futures_total"], round(3488.7164 - 2.65, 4))
            self.assertEqual(capital["spot_usdt_total"], 1000.0)
            self.assertEqual(capital["spot_usdc_total"], 0.0)
            self.assertEqual(capital["total"], round(1000.0 + 3488.7164 - 2.65, 4))
        finally:
            _reload_capital_modules(None)

    def test_ui_capital_uses_only_binance_summary_fields(self):
        view = _reload_capital_modules("USDT,USDC")
        try:
            spot = {
                "balances": {
                    "USDT": {"free": 5000.0, "locked": 0.0},
                    "USDC": {"free": 5000.0, "locked": 0.0},
                },
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
            capital = view.build_ui_capital(spot, futures)
            self.assertEqual(capital["source"], "binance_rest")
            self.assertEqual(capital["spot_usdt_total"], 5000.0)
            self.assertEqual(capital["spot_usdc_total"], 5000.0)
            self.assertEqual(capital["futures_total"], 9323.0)
            self.assertEqual(capital["total"], 19323.0)
        finally:
            _reload_capital_modules(None)

    def test_usdt_only_spot_ignores_usdc_and_btc(self):
        view = _reload_capital_modules("USDT")
        try:
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
            capital = view.build_ui_capital(spot, {})
            self.assertEqual(capital["spot_usdt_total"], 5000.0)
            self.assertEqual(capital["spot_usdc_total"], 0.0)
            self.assertEqual(capital["spot_stable_total"], 5000.0)
            self.assertEqual(capital["total"], 5000.0)
        finally:
            _reload_capital_modules(None)

    def test_treasury_totals_from_balances_helper(self):
        view = _reload_capital_modules("USDT")
        usdt, usdc, total = view.treasury_totals_from_balances(
            {"USDT": {"free": 1, "locked": 2}, "USDC": {"free": 3, "locked": 0}, "ETH": {"free": 9, "locked": 0}}
        )
        self.assertEqual((usdt, usdc, total), (3.0, 0.0, 3.0))
        _reload_capital_modules(None)

    def test_futures_equity_usdt_row_when_usdt_only(self):
        view = _reload_capital_modules("USDT")
        try:
            equity = view.futures_equity_from_account(
                {
                    "exchange_account": {"totalMarginBalance": 9257.0},
                    "balance_assets": [
                        {"asset": "USDT", "balance": 3488.0, "cross_wallet_balance": 3488.0, "cross_unrealized_pnl": -2.65},
                    ],
                }
            )
            self.assertEqual(equity, round(3488.0 - 2.65, 4))
        finally:
            _reload_capital_modules(None)

    def test_futures_equity_prefers_exchange_margin_balance_when_multi_asset(self):
        view = _reload_capital_modules("USDT,USDC")
        try:
            equity = view.futures_equity_from_account(
                {
                    "margin_total": 100.0,
                    "exchange_account": {"totalMarginBalance": 9323.0},
                }
            )
            self.assertEqual(equity, 9323.0)
        finally:
            _reload_capital_modules(None)


if __name__ == "__main__":
    unittest.main()
