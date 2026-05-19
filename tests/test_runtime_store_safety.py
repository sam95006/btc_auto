import shutil
import tempfile
import unittest
from pathlib import Path

from backend.services.runtime_store import RuntimeStateStore


class RuntimeStoreSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="nexus_runtime_store_"))
        self.db_path = self.temp_dir / "runtime.db"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_snapshot_version_and_last_writer_increment(self):
        store = RuntimeStateStore(str(self.db_path))
        store.save_snapshot({"system": {"running": True}}, writer="worker-a", single_instance=True)
        first = store.load_snapshot()
        self.assertEqual(first["runtime"]["snapshot_version"], 1)
        self.assertEqual(first["runtime"]["last_writer"], "worker-a")
        self.assertTrue(first["runtime"]["single_instance"])

        store.save_snapshot({"system": {"running": False}}, writer="worker-b", single_instance=True)
        second = store.load_snapshot()
        self.assertEqual(second["runtime"]["snapshot_version"], 2)
        self.assertEqual(second["runtime"]["last_writer"], "worker-b")

    def test_multiple_store_instances_do_not_drop_runtime_metadata(self):
        first_store = RuntimeStateStore(str(self.db_path))
        second_store = RuntimeStateStore(str(self.db_path))
        first_store.save_snapshot({"system": {"running": True}}, writer="writer-1", single_instance=True)
        second_store.save_snapshot({"system": {"running": True}}, writer="writer-2", single_instance=False)
        snapshot = second_store.load_snapshot()
        self.assertEqual(snapshot["runtime"]["last_writer"], "writer-2")
        self.assertEqual(snapshot["runtime"]["snapshot_version"], 2)
        self.assertFalse(snapshot["runtime"]["single_instance"])


if __name__ == "__main__":
    unittest.main()
