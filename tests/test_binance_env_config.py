import os
import unittest
from unittest.mock import patch

from backend.trading.trading_mode import TradingModeSafetyError, get_trading_mode, require_testnet_credentials


class BinanceEnvConfigTests(unittest.TestCase):
    def test_paper_mode_does_not_require_keys(self):
        with patch.dict(os.environ, {"NEXUS_TRADING_MODE": "paper"}, clear=False):
            self.assertEqual(get_trading_mode(), "paper")

    def test_binance_testnet_mode_requires_spot_and_futures_keys(self):
        env = {
            "NEXUS_TRADING_MODE": "binance_testnet",
            "BINANCE_SPOT_TESTNET_API_KEY": "",
            "BINANCE_SPOT_TESTNET_SECRET_KEY": "",
            "BINANCE_FUTURES_TESTNET_API_KEY": "",
            "BINANCE_FUTURES_TESTNET_SECRET_KEY": "",
        }
        with patch.dict(os.environ, env, clear=False):
            missing = require_testnet_credentials()
        self.assertIn("spot", missing)
        self.assertIn("futures", missing)

    def test_live_mode_is_forbidden(self):
        with patch.dict(os.environ, {"NEXUS_TRADING_MODE": "live"}, clear=False):
            with self.assertRaises(TradingModeSafetyError):
                get_trading_mode()


if __name__ == "__main__":
    unittest.main()
