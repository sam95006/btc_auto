import json
import unittest

from backend.trading.binance_spot_user_stream_manager import BinanceSpotUserStreamManager, SpotStreamMaintenanceError


class _FakeSpotClient:
    def __init__(self):
        self.listen_key_counter = 0
        self.closed = []
        self.keepalive_fail = None

    def is_configured(self):
        return True

    def create_listen_key(self):
        self.listen_key_counter += 1
        return f"test-listen-key-{self.listen_key_counter}"

    def keepalive_listen_key(self, listen_key):
        if self.keepalive_fail:
            raise RuntimeError(self.keepalive_fail)
        return {"listenKey": listen_key}

    def close_listen_key(self, listen_key):
        self.closed.append(listen_key)
        return {}

    def build_user_stream_url(self, listen_key):
        return f"wss://example.com/ws/{listen_key}"


class SpotUserStreamManagerTests(unittest.TestCase):
    def test_event_tracking_and_health_snapshot(self):
        manager = BinanceSpotUserStreamManager(_FakeSpotClient())
        manager._record_event(json.dumps({"e": "executionReport", "i": 1}))
        manager.reconcile_rest_snapshot()
        health = manager.health_snapshot()
        self.assertEqual(health["status"], "connected")
        self.assertTrue(health["connected"])
        self.assertEqual(health["event_counts"]["executionReport"], 1)
        self.assertGreaterEqual(health["last_rest_reconcile_time"], 0)

    def test_error_enters_reconnecting_backoff_flow(self):
        manager = BinanceSpotUserStreamManager(_FakeSpotClient(), reconnect_base_delay=1.0, reconnect_max_delay=30.0)
        manager._record_error(RuntimeError("socket dropped"))
        manager._reconnect_attempt = 3
        health = manager.health_snapshot()
        self.assertEqual(health["status"], "degraded")
        self.assertIn("socket dropped", health["errors"][-1])
        self.assertEqual(manager._backoff_seconds(), 4.0)

    def test_listen_key_expiry_resets_and_recreates(self):
        client = _FakeSpotClient()
        manager = BinanceSpotUserStreamManager(client)
        first = manager._ensure_listen_key()
        manager._invalidate_listen_key("expired")
        second = manager._ensure_listen_key()
        health = manager.health_snapshot()
        self.assertNotEqual(first, second)
        self.assertEqual(client.closed, [first])
        self.assertEqual(health["status"], "reconnecting")
        self.assertFalse(health["connected"])

    def test_keepalive_410_marks_reconnecting(self):
        client = _FakeSpotClient()
        client.keepalive_fail = "HTTP 410 Gone"
        manager = BinanceSpotUserStreamManager(client)
        manager._ensure_listen_key()
        manager._last_keepalive = 0
        with self.assertRaises(SpotStreamMaintenanceError):
            manager._keepalive_if_needed()
        health = manager.health_snapshot()
        self.assertEqual(health["status"], "degraded")
        self.assertFalse(health["listen_key_active"])
        self.assertEqual(health["truth_mode"], "rest_only")
        self.assertIn("410", "".join(health["errors"]))


if __name__ == "__main__":
    unittest.main()
