import shutil
import tempfile
import unittest
from pathlib import Path

from backend.runtime.single_instance_guard import SingleInstanceError, SingleInstanceGuard


class ProcessSingletonTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="nexus_singleton_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_same_name_cannot_be_acquired_twice(self):
        first = SingleInstanceGuard("test_lock", lock_dir=self.temp_dir).acquire()
        try:
            with self.assertRaises(SingleInstanceError):
                SingleInstanceGuard("test_lock", lock_dir=self.temp_dir).acquire()
        finally:
            first.release()

    def test_release_allows_reacquire(self):
        first = SingleInstanceGuard("test_lock", lock_dir=self.temp_dir).acquire()
        first.release()
        second = SingleInstanceGuard("test_lock", lock_dir=self.temp_dir).acquire()
        second.release()


if __name__ == "__main__":
    unittest.main()
