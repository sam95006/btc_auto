import unittest

from backend.services.nexus_runtime import NexusRuntime


class ExchangeSyncTests(unittest.TestCase):
    def test_fleet_for_futures_symbol_maps_core_and_radar(self):
        runtime = NexusRuntime.__new__(NexusRuntime)
        core_map = {"BTCUSDT": "BTC", "ETHUSDT": "ETH"}
        self.assertEqual(runtime._fleet_for_futures_symbol("ETHUSDT", core_map), "ETH")
        self.assertEqual(runtime._fleet_for_futures_symbol("XRPUSDT", core_map), "RADAR")
        self.assertEqual(runtime._fleet_for_futures_symbol("BNBUSDT", core_map), "RADAR")


if __name__ == "__main__":
    unittest.main()
