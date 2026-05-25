import os
import unittest

from config.runtime_config import always_on_trading_enabled


class RuntimeConfigTests(unittest.TestCase):
    def test_always_on_env(self):
        os.environ["NEXUS_ALWAYS_ON_TRADING"] = "1"
        self.assertTrue(always_on_trading_enabled())
        os.environ["NEXUS_ALWAYS_ON_TRADING"] = "0"
        self.assertFalse(always_on_trading_enabled())


if __name__ == "__main__":
    unittest.main()
