import unittest

from backend.market.binance_futures_symbol_map import coingecko_row_to_binance_symbol


class CoinGeckoSymbolMapTests(unittest.TestCase):
    def test_maps_common_ids_to_binance_symbols(self):
        self.assertEqual(coingecko_row_to_binance_symbol({"id": "binancecoin", "symbol": "bnb"}), "BNBUSDT")
        self.assertEqual(coingecko_row_to_binance_symbol({"id": "ethereum", "symbol": "eth"}), "ETHUSDT")
        self.assertEqual(coingecko_row_to_binance_symbol({"id": "ripple", "symbol": "xrp"}), "XRPUSDT")

    def test_skips_stablecoins(self):
        self.assertEqual(coingecko_row_to_binance_symbol({"id": "tether", "symbol": "usdt"}), "")


if __name__ == "__main__":
    unittest.main()
