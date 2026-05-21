import unittest

from config.fleet_routing_config import (
    fleet_for_exchange_position,
    validate_futures_open_route,
)


class FleetRoutingTests(unittest.TestCase):
    def test_core_fleets_only_open_own_symbols(self):
        ok, _ = validate_futures_open_route("ETH", "ETHUSDT")
        self.assertTrue(ok)
        ok, reason = validate_futures_open_route("BTC", "ETHUSDT")
        self.assertFalse(ok)
        self.assertIn("owned_by", reason)

    def test_radar_opens_alt_only(self):
        ok, _ = validate_futures_open_route("RADAR", "XRPUSDT")
        self.assertTrue(ok)
        ok, reason = validate_futures_open_route("RADAR", "BTCUSDT")
        self.assertFalse(ok)
        self.assertEqual(reason, "radar_cannot_open_core_symbol")
        ok, reason = validate_futures_open_route("ETH", "XRPUSDT")
        self.assertFalse(ok)
        self.assertEqual(reason, "alt_symbol_must_use_radar")

    def test_exchange_position_mapping(self):
        core_map = {"BTCUSDT": "BTC", "ETHUSDT": "ETH"}
        self.assertEqual(fleet_for_exchange_position("XRPUSDT", core_map), "RADAR")
        self.assertEqual(fleet_for_exchange_position("ETHUSDT", core_map), "ETH")


if __name__ == "__main__":
    unittest.main()
