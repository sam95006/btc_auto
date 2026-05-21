import unittest

from config.fleet_routing_config import fleet_for_exchange_position


class ExchangeSyncTests(unittest.TestCase):
    def test_fleet_for_futures_symbol_maps_core_and_radar(self):
        core_map = {"BTCUSDT": "BTC", "ETHUSDT": "ETH"}
        self.assertEqual(fleet_for_exchange_position("ETHUSDT", core_map), "ETH")
        self.assertEqual(fleet_for_exchange_position("XRPUSDT", core_map), "RADAR")
        self.assertEqual(fleet_for_exchange_position("BNBUSDT", core_map), "RADAR")


if __name__ == "__main__":
    unittest.main()
