import shutil
import tempfile
import unittest
from pathlib import Path

from backend.services.runtime_store import RuntimeStateStore
from backend.trading.binance_sync_models import FuturesAccountSnapshot, SpotAccountSnapshot


class BinanceSnapshotShapeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="nexus_snapshot_shape_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_runtime_default_snapshot_keeps_old_and_new_keys(self):
        store = RuntimeStateStore(str(self.temp_dir / "shape.db"))
        snapshot = store.default_snapshot()
        for key in ("system", "capital", "positions", "orders", "trades", "alerts"):
            self.assertIn(key, snapshot)
        for key in ("binance_sync", "learning_status", "validation_status", "normalized_events", "agent_advisory", "llm_status", "account_sync_status", "leverage_status", "truth_layer_status", "market_context", "radar_scan", "portfolio_status", "station_learning_exchange", "runtime"):
            self.assertIn(key, snapshot)

    def test_runtime_load_snapshot_backfills_new_keys(self):
        store = RuntimeStateStore(str(self.temp_dir / "shape.db"))
        legacy_snapshot = {
            "system": {"running": True},
            "capital": {"total": 123.0},
            "positions": [],
            "orders": [],
            "trades": [],
            "alerts": [],
        }
        store.save_snapshot(legacy_snapshot)
        snapshot = store.load_snapshot()
        self.assertTrue(snapshot["system"]["running"])
        self.assertEqual(snapshot["capital"]["total"], 123.0)
        self.assertIn("binance_sync", snapshot)
        self.assertIn("learning_status", snapshot)
        self.assertIn("validation_status", snapshot)
        self.assertIn("normalized_events", snapshot)
        self.assertIn("agent_advisory", snapshot)
        self.assertIn("llm_status", snapshot)
        self.assertIn("account_sync_status", snapshot)
        self.assertIn("leverage_status", snapshot)
        self.assertIn("truth_layer_status", snapshot)
        self.assertIn("market_context", snapshot)
        self.assertIn("radar_scan", snapshot)
        self.assertIn("portfolio_status", snapshot)
        self.assertIn("station_learning_exchange", snapshot)
        self.assertIn("runtime", snapshot)
        self.assertIn("spot_stream_health", snapshot["account_sync_status"])
        self.assertIn("spot_truth_mode", snapshot["account_sync_status"])
        self.assertIn("futures_truth_mode", snapshot["account_sync_status"])
        self.assertIn("spot_truth_scope", snapshot["account_sync_status"])
        self.assertIn("spot_allowed_assets", snapshot["account_sync_status"])
        self.assertIn("spot_excluded_assets_count", snapshot["account_sync_status"])

    def test_spot_snapshot_schema(self):
        snapshot = SpotAccountSnapshot(
            balances={"USDT": {"free": 100.0, "locked": 0.0}},
            free={"USDT": 100.0},
            locked={"USDT": 0.0},
            total_equity_usdt=100.0,
            open_orders=[],
            trade_history=[],
            last_sync_time=123,
            sync_status="connected",
            sync_error="",
        ).to_dict()
        expected = {
            "account_type",
            "balances",
            "free",
            "locked",
            "total_equity_usdt",
            "open_orders",
            "trade_history",
            "last_sync_time",
            "sync_status",
            "sync_error",
        }
        self.assertTrue(expected.issubset(snapshot.keys()))

    def test_futures_snapshot_schema(self):
        snapshot = FuturesAccountSnapshot(
            total_wallet_balance=100.0,
            available_balance=80.0,
            total_unrealized_profit=5.0,
            total_margin_balance=105.0,
            positions=[],
            open_orders=[],
            order_updates=[],
            fills=[],
            funding_rates=[],
            last_sync_time=123,
            sync_status="connected",
            sync_error="",
        ).to_dict()
        expected = {
            "account_type",
            "total_wallet_balance",
            "available_balance",
            "total_unrealized_profit",
            "total_margin_balance",
            "positions",
            "open_orders",
            "order_updates",
            "fills",
            "funding_rates",
            "last_sync_time",
            "sync_status",
            "sync_error",
        }
        self.assertTrue(expected.issubset(snapshot.keys()))

    def test_round_table_memory_can_persist_station_learning_fields(self):
        store = RuntimeStateStore(str(self.temp_dir / "memory.db"))
        memory = {
            "meeting_time": "2026-05-18 12:00:00",
            "market_summary": "summary",
            "risk_level": "NORMAL",
            "enabled_strategies": ["adaptive_signal_fusion"],
            "disabled_strategies": [],
            "fleet_restrictions": {"BTC": {"allowed_new_entries": True}},
            "capital_adjustments": {"BTC": {"capital_multiplier": 0.8}},
            "reserve_action": "hold",
            "station_shares": [{"station": "HQ"}],
            "cross_station_lessons": [{"lesson_type": "portfolio_risk"}],
            "opportunity_board": [{"symbol": "BTCUSDT"}],
            "hedge_recommendations": [{"hedge_symbol": "ETHUSDT"}],
            "reason": "test",
            "timestamp": "2026-05-18 12:00:00",
        }
        store.save_round_table_decision_memory(memory)
        rows = store.recent_round_table_decision_memory(limit=1)
        self.assertEqual(rows[0]["station_shares"][0]["station"], "HQ")
        self.assertEqual(rows[0]["hedge_recommendations"][0]["hedge_symbol"], "ETHUSDT")


if __name__ == "__main__":
    unittest.main()
