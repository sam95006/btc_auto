import unittest
from unittest.mock import MagicMock, patch

from backend.trading.binance_futures_testnet_client import (
    BinanceFuturesTestnetClient,
    BinanceTestnetError,
    _clean_credential,
)


class BinanceFuturesCloseTests(unittest.TestCase):
    def test_clean_credential_strips_quotes_and_newlines(self):
        self.assertEqual(_clean_credential('"abc123"\n'), "abc123")
        self.assertEqual(_clean_credential("'secret'"), "secret")

    def test_close_open_position_one_way_mode(self):
        client = BinanceFuturesTestnetClient(api_key="k", api_secret="s")
        client.get_all_position_risk = MagicMock(
            return_value=[
                {
                    "symbol": "ETHUSDT",
                    "positionAmt": "0.05",
                    "positionSide": "BOTH",
                    "entryPrice": "3000",
                    "markPrice": "2900",
                }
            ]
        )
        client.get_dual_side_position = MagicMock(return_value=False)
        client.normalize_quantity = MagicMock(return_value=0.05)
        client.place_market_order = MagicMock(return_value={"orderId": 99, "status": "FILLED"})

        order = client.close_open_position_market("ETHUSDT", client_order_id="test_close")
        self.assertEqual(order["orderId"], 99)
        client.place_market_order.assert_called_once()
        kwargs = client.place_market_order.call_args.kwargs
        self.assertEqual(kwargs["side"], "SELL")
        self.assertTrue(kwargs["reduce_only"])
        self.assertTrue(kwargs["omit_position_side"])

    def test_close_open_position_hedge_mode_retries(self):
        client = BinanceFuturesTestnetClient(api_key="k", api_secret="s")
        client.get_all_position_risk = MagicMock(
            return_value=[
                {
                    "symbol": "ETHUSDT",
                    "positionAmt": "0.05",
                    "positionSide": "LONG",
                    "entryPrice": "3000",
                    "markPrice": "2900",
                }
            ]
        )
        client.get_dual_side_position = MagicMock(return_value=True)
        client.normalize_quantity = MagicMock(return_value=0.05)

        def _place(**kwargs):
            if kwargs.get("position_side") == "LONG":
                raise BinanceTestnetError("Binance testnet error -1109: Invalid account")
            return {"orderId": 42, "status": "FILLED"}

        client.place_market_order = MagicMock(side_effect=_place)
        order = client.close_open_position_market("ETHUSDT")
        self.assertEqual(order["orderId"], 42)
        self.assertGreaterEqual(client.place_market_order.call_count, 2)


if __name__ == "__main__":
    unittest.main()
