import shutil
import tempfile
import unittest
from pathlib import Path

from backend.trading.order_idempotency_guard import OrderIdempotencyGuard


class OrderIdempotencyGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="nexus_idempotency_"))
        self.db_path = self.temp_dir / "idempotency.db"
        self.guard = OrderIdempotencyGuard(str(self.db_path), window_seconds=30)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_duplicate_order_blocked_within_same_window(self):
        ok, fingerprint = self.guard.claim("BTC", "BTCUSDT", "BUY", "signal-1", timestamp=100.0)
        self.assertTrue(ok)
        again, duplicate_fp = self.guard.claim("BTC", "BTCUSDT", "BUY", "signal-1", timestamp=110.0)
        self.assertFalse(again)
        self.assertEqual(fingerprint, duplicate_fp)

    def test_different_signal_hash_is_allowed(self):
        first, _ = self.guard.claim("BTC", "BTCUSDT", "BUY", "signal-1", timestamp=100.0)
        second, _ = self.guard.claim("BTC", "BTCUSDT", "BUY", "signal-2", timestamp=100.0)
        self.assertTrue(first)
        self.assertTrue(second)


if __name__ == "__main__":
    unittest.main()
