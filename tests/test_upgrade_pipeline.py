import os
import tempfile
import unittest
from unittest.mock import patch

from backend.governance.execution_governor import ExecutionGovernor
from backend.governance.trade_proposal_service import TradeProposalService
from backend.governance.upgrade_pipeline import UpgradePipeline
from backend.learning.learning_review_queue import LearningReviewQueue
from backend.market.universe_filter_service import UniverseFilterService
from backend.news.event_registry import EventRegistry
from backend.services.runtime_store import RuntimeStateStore


class UpgradePipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.store = RuntimeStateStore(db_path=self.tmp.name)
        self.pipeline = UpgradePipeline(self.store)

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except Exception:
            pass

    def test_event_registry_registers_events(self):
        events = [{"event_id": "a1", "bucket": "crypto", "major": True, "impact": "HIGH"}]
        snap = EventRegistry().register_batch(events)
        self.assertEqual(snap["event_count"], 1)
        self.assertEqual(snap["major_event_count"], 1)

    def test_universe_filter_returns_symbols(self):
        symbols = UniverseFilterService(max_symbols=10).resolve_scan_symbols()
        self.assertGreaterEqual(len(symbols), 4)
        self.assertTrue(all(sym.endswith("USDT") for sym in symbols))

    def test_decision_trace_persisted(self):
        proposal = {"fleet": "BTC", "symbol": "BTCUSDT", "side": "BUY", "strategy_key": "btc_adaptive_strategy"}
        validation = {"approved": True, "reason": "ok", "stages": {}}
        governed, trace = self.pipeline.govern_validation(proposal, validation)
        self.assertTrue(governed.get("trace_id"))
        traces = self.store.recent_decision_traces(limit=5)
        self.assertEqual(traces[0]["trace_id"], trace["trace_id"])

    def test_learning_review_auto_apply(self):
        os.environ["NEXUS_LEARNING_AUTO_APPLY"] = "1"
        os.environ["NEXUS_LEARNING_AUTO_APPROVE"] = "1"
        queue = LearningReviewQueue(self.store)
        rec = {
            "timestamp": "2026-01-01 00:00:00",
            "fleet": "ETH",
            "symbol": "ETHUSDT",
            "strategy_key": "eth_adaptive_strategy",
            "signal_weight_adjustment": -0.03,
            "strategy_confidence_adjustment": -0.03,
        }
        item = queue.enqueue_from_recommendation(rec)
        self.assertEqual(item.get("status"), "approved")
        patches = self.store.list_applied_learning_patches(limit=5)
        self.assertGreaterEqual(len(patches), 1)

    def test_trade_proposal_service(self):
        svc = TradeProposalService(self.store)
        svc.begin_tick()
        proposal = svc.create_from_request({"fleet": "SOL", "symbol": "SOLUSDT", "side": "BUY", "margin": 50})
        self.assertTrue(proposal.get("proposal_id"))
        self.assertEqual(len(svc.recent(limit=5)), 1)

    def test_execution_governor_blocks_learning_pause(self):
        with patch.dict(os.environ, {"NEXUS_TESTNET_SANDBOX": "0"}, clear=False):
            gov = ExecutionGovernor(shadow_mode_enabled=False)
            out = gov.evaluate(
                {"fleet": "BTC"},
                {"approved": True, "reason": "ok"},
                learning_guidance={"pause_new_entries": True},
            )
            self.assertFalse(out.get("approved"))


if __name__ == "__main__":
    unittest.main()
