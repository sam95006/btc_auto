import unittest
from unittest.mock import patch

from config.wallet_baseline_config import FUTURES_BASELINE_CAPITAL, SPOT_BASELINE_CAPITAL


class WalletBaselineConfigTests(unittest.TestCase):
    @patch.dict("os.environ", {"NEXUS_FUTURES_BASELINE_CAPITAL": "5000", "NEXUS_SPOT_BASELINE_CAPITAL": "5000"}, clear=False)
    def test_defaults_match_user_testnet(self):
        import importlib
        import config.wallet_baseline_config as cfg

        importlib.reload(cfg)
        self.assertEqual(cfg.FUTURES_BASELINE_CAPITAL, 5000.0)
        self.assertEqual(cfg.SPOT_BASELINE_CAPITAL, 5000.0)


if __name__ == "__main__":
    unittest.main()
