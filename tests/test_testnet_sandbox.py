import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.services.runtime_store import RuntimeStateStore
class TestnetSandboxTests(unittest.TestCase):
    def test_sandbox_mode_active_with_testnet_flag(self):
        with patch.dict("os.environ", {"NEXUS_TESTNET_SANDBOX": "1"}, clear=False):
            from importlib import reload

            import config.testnet_sandbox_config as tsc
            from backend.trading.sandbox_mode import sandbox_active

            reload(tsc)
            import backend.trading.sandbox_mode as sm

            reload(sm)
            self.assertTrue(sandbox_active())

    def test_clear_negative_trade_results(self):
        tmp = Path(tempfile.mkdtemp(prefix="nexus_sandbox_"))
        db_path = tmp / "sandbox.db"
        try:
            store = RuntimeStateStore(str(db_path))
            store.append_trade_result({"pnl": -5.0, "symbol": "BTCUSDT", "fleet": "BTC"})
            store.append_trade_result({"pnl": 2.0, "symbol": "BTCUSDT", "fleet": "BTC"})
            removed = store.clear_negative_trade_results()
            self.assertEqual(removed, 1)
            rows = store.recent_trade_results(limit=10)
            self.assertEqual(len(rows), 1)
            self.assertGreater(float(rows[0].get("pnl") or 0), 0)
        finally:
            try:
                db_path.unlink(missing_ok=True)
            except Exception:
                pass

    def test_sandbox_skips_symbol_cooldown_hard_block(self):
        with patch.dict("os.environ", {"NEXUS_TESTNET_SANDBOX": "1"}, clear=False):
            from importlib import reload

            import config.testnet_sandbox_config as tsc
            import backend.trading.trade_validation_pipeline as tvp

            reload(tsc)
            reload(tvp)
            from backend.trading.trade_validation_pipeline import _hard_learning_block

            blocked, reason = _hard_learning_block(
                "BTCUSDT",
                {
                    "symbol_cooldown": {
                        "BTCUSDT": {"active": True, "reason": "repeated_symbol_losses"},
                    }
                },
            )
            self.assertFalse(blocked)
            self.assertIsNone(reason)

    def test_execution_governor_allows_sandbox_live(self):
        with patch.dict("os.environ", {"NEXUS_TESTNET_SANDBOX": "1", "NEXUS_SANDBOX_FORCE_LIVE": "1"}, clear=False):
            from importlib import reload

            import config.testnet_sandbox_config as tsc
            import backend.governance.execution_governor as eg

            reload(tsc)
            reload(eg)
            from backend.governance.execution_governor import ExecutionGovernor

            gov = ExecutionGovernor(shadow_mode_enabled=True)
            out = gov.evaluate(
                {"fleet": "BTC", "symbol": "BTCUSDT"},
                {"approved": True, "reason": "validated_for_execution"},
                learning_guidance={"pause_new_entries": True},
            )
            self.assertTrue(out.get("approved"))


if __name__ == "__main__":
    unittest.main()
