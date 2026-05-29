import os
import tempfile
import unittest

from backend.decision.batched_decision_trace_writer import BatchedDecisionTraceWriter
from backend.governance.autonomy_bounds_guard import clamp_learning_patch, clamp_trade_proposal
from backend.risk.volatility_position_sizer import VolatilityPositionSizer
from backend.services.live_snapshot_cache import LiveSnapshotCache
from backend.services.runtime_store import RuntimeStateStore


class InfraCacheBoundsTests(unittest.TestCase):
    def test_live_snapshot_cache_roundtrip(self):
        cache = LiveSnapshotCache()
        cache.put({"system": {"mode": "test"}, "runtime": {"x": 1}})
        loaded = cache.get()
        self.assertEqual(loaded["system"]["mode"], "test")

    def test_snapshot_memory_read_before_db_flush(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        store = RuntimeStateStore(db_path=tmp.name)
        store.save_snapshot({"system": {"mode": "mem"}}, flush_now=False)
        self.assertEqual(store.load_snapshot()["system"]["mode"], "mem")
        store.save_snapshot({"system": {"mode": "disk"}}, flush_now=True)
        self.assertEqual(store.load_snapshot()["system"]["mode"], "disk")
        store._conn.close()
        os.unlink(tmp.name)

    def test_batched_decision_traces(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        store = RuntimeStateStore(db_path=tmp.name)
        writer = BatchedDecisionTraceWriter(store, flush_seconds=9999, max_buffer=1000)
        writer.enqueue({"trace_id": "t1", "timestamp": "2026-01-01 00:00:00", "approved": True})
        self.assertEqual(writer.pending_count(), 1)
        self.assertEqual(writer.flush(), 1)
        traces = store.recent_decision_traces(limit=3)
        self.assertEqual(traces[0]["trace_id"], "t1")
        store._conn.close()
        os.unlink(tmp.name)

    def test_autonomy_bounds_clamp_leverage(self):
        proposal, warnings = clamp_trade_proposal({"leverage": 99.0, "margin": 50.0})
        self.assertLessEqual(proposal["leverage"], 10.0)
        self.assertTrue(warnings)

    def test_volatility_sizer_reduces_high_vol_symbol(self):
        sizer = VolatilityPositionSizer()
        contexts = {
            "BTC": {"atr_pct": 0.01},
            "PEPE": {"atr_pct": 0.05},
        }
        mult = sizer.margin_multiplier(contexts["PEPE"], contexts)
        self.assertLess(mult, 0.5)
        req = sizer.apply_to_request({"margin": 100.0, "fleet": "PEPE"}, contexts["PEPE"], contexts)
        self.assertLess(req["margin"], 100.0)


if __name__ == "__main__":
    unittest.main()
