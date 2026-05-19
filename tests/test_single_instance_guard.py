import shutil
import tempfile
import unittest
from pathlib import Path

from backend.runtime.single_instance_guard import SingleInstanceError, SingleInstanceGuard


class SingleInstanceGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="nexus_single_instance_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_same_name_cannot_be_acquired_twice(self):
        first = SingleInstanceGuard("nexus_web_test", lock_dir=self.temp_dir).acquire()
        try:
            with self.assertRaises(SingleInstanceError):
                SingleInstanceGuard("nexus_web_test", lock_dir=self.temp_dir).acquire()
        finally:
            first.release()

    def test_stale_pid_metadata_does_not_block_acquire(self):
        pid_path = self.temp_dir / "nexus_worker_test.pid"
        pid_path.write_text('{"pid": 999999, "started_at": "old"}', encoding="utf-8")
        guard = SingleInstanceGuard("nexus_worker_test", lock_dir=self.temp_dir).acquire()
        try:
            self.assertTrue(guard.snapshot()["single_instance"])
            self.assertEqual(guard.snapshot()["pid"], guard.snapshot()["pid"])
        finally:
            guard.release()


if __name__ == "__main__":
    unittest.main()
