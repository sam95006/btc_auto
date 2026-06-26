"""Stage 3 post-run P0/P1 fix regression tests."""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


class Stage3RepeatedGateDedupTests(unittest.TestCase):
    def test_same_setup_10_polls_counts_one_blocked_event(self) -> None:
        from tools.research.stage3_learning_loop import Stage3LearningLoop, setup_key

        with tempfile.TemporaryDirectory() as tmp:
            loop = Stage3LearningLoop(Path(tmp))
            symbol, side, regime = "ETHUSDT", "BUY", "range_low"
            failure_reason = "stop_loss_hit"
            decision_source = "controlled_demo_order"
            loop.record_loss_reflection_patch(
                decision_id="d1",
                trade={
                    "symbol": symbol,
                    "side": side,
                    "decision_source": decision_source,
                    "confidence_before": 0.8,
                    "position_size_before": 10.0,
                    "close_pnl": -2.0,
                    "signal_id": "s1",
                    "order_id": "o1",
                },
                regime=regime,
                failure_reason=failure_reason,
            )
            for _ in range(10):
                result = loop.evaluate_same_setup(
                    symbol=symbol,
                    side=side,
                    regime=regime,
                    failure_reason=failure_reason,
                    decision_source=decision_source,
                )
                self.assertTrue(result["skip_trade"])
            self.assertEqual(loop.state.stats["repeated_mistake_blocked_count"], 1)
            self.assertEqual(loop.state.stats["repeated_mistake_detected_count"], 1)
            self.assertEqual(loop.state.stats["blocked_ticks_count"], 10)


class Stage3PatchSemanticsTests(unittest.TestCase):
    def test_first_loss_risk_reduce_second_attempt_blocked(self) -> None:
        from tools.research.stage3_learning_loop import Stage3LearningLoop, setup_key

        with tempfile.TemporaryDirectory() as tmp:
            loop = Stage3LearningLoop(Path(tmp))
            symbol, side, regime = "ETHUSDT", "BUY", "range_low"
            failure_reason = "stop_loss_hit"
            decision_source = "controlled_demo_order"
            trade = {
                "symbol": symbol,
                "side": side,
                "decision_source": decision_source,
                "confidence_before": 0.8,
                "position_size_before": 10.0,
                "close_pnl": -2.0,
            }
            loop.record_loss_reflection_patch(
                decision_id="d1",
                trade=trade,
                regime=regime,
                failure_reason=failure_reason,
            )
            patch = loop.state.patches[setup_key(symbol, side, regime, failure_reason, decision_source)]
            self.assertEqual(patch["action"], "risk_reduce")

            second = loop.evaluate_same_setup(
                symbol=symbol,
                side=side,
                regime=regime,
                failure_reason=failure_reason,
                decision_source=decision_source,
            )
            self.assertTrue(second["skip_trade"])
            self.assertTrue(second["repeated_mistake_blocked"])
            self.assertGreater(loop.state.stats["repeated_mistake_detected_count"], 0)
            self.assertGreater(loop.state.stats["repeated_mistake_blocked_count"], 0)


class Stage3Validator24hTests(unittest.TestCase):
    def test_24h_validator_accepts_multi_orders_and_gap_review(self) -> None:
        from tools.research.stage3_learning_loop import OUTPUT_FILES
        from tools.research.validate_stage3_demo_learning_outputs import validate

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for name in OUTPUT_FILES:
                if name == "demo_order_session_report.json":
                    (out / name).write_text(json.dumps({"open_positions_after": 0, "position_closed": True}), encoding="utf-8")
                    continue
                (out / name).write_text("" if name.endswith(".jsonl") else "{}", encoding="utf-8")

            audit = {
                "mode": "demo-order",
                "max_orders": 2,
                "orders_sent": 2,
                "is_24h_run": True,
                "session_reports": [
                    {
                        "demo_order_sent": True,
                        "position_closed": True,
                        "open_positions_after": 0,
                        "reconciliation_status": "gap_detected",
                        "requires_manual_review": True,
                        "run_reconciliation": True,
                        "per_trade_reconciliation": True,
                    },
                    {
                        "demo_order_sent": True,
                        "position_closed": True,
                        "open_positions_after": 0,
                        "reconciliation_status": "matched",
                    },
                ],
            }
            (out / "runner_audit.json").write_text(json.dumps(audit), encoding="utf-8")
            (out / "stop_conditions.json").write_text(json.dumps({"triggered": []}), encoding="utf-8")

            snapshots = [
                {
                    "balance_read_ok": True,
                    "coin": "USDT",
                    "total_equity": 100,
                    "wallet_balance": 100,
                    "available_balance": 100,
                }
            ]
            with (out / "account_snapshots.jsonl").open("w", encoding="utf-8") as fh:
                for row in snapshots:
                    fh.write(json.dumps(row) + "\n")

            trades = []
            for i in range(2):
                trades.append(
                    {
                        "decision_id": f"d{i}",
                        "signal_id": f"s{i}",
                        "order_id": f"o{i}",
                        "symbol": "ETHUSDT",
                        "side": "BUY",
                        "entry_price": 1,
                        "exit_price": 1,
                        "close_pnl": -1,
                        "exit_reason": "stop",
                        "confidence_before": 0.8,
                        "confidence_after": 0.7,
                        "position_size_before": 10,
                        "position_size_after": 8,
                        "reflection_created": True,
                        "patch_created": True,
                        "patch_applied_to_next_decision": False,
                        "repeated_mistake_detected": False,
                        "repeated_mistake_blocked": False,
                        "demo_order_sent": True,
                        "position_closed": True,
                        "reconciliation_status": "gap_detected" if i == 0 else "matched",
                    }
                )
            with (out / "trade_results.jsonl").open("w", encoding="utf-8") as fh:
                for row in trades:
                    fh.write(json.dumps(row) + "\n")

            with (out / "orders.jsonl").open("w", encoding="utf-8") as fh:
                for i in range(2):
                    fh.write(
                        json.dumps(
                            {
                                "order_id": f"o{i}",
                                "demo_order_sent": True,
                                "stop_loss_attached": True,
                                "mainnet": False,
                                "real_money": False,
                            }
                        )
                        + "\n"
                    )

            with (out / "decisions.jsonl").open("w", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {
                            "balance_snapshot_id": "s1",
                            "account_total_equity": 100,
                            "account_available_balance": 100,
                        }
                    )
                    + "\n"
                )

            result = validate(out, require_balance=True, require_24h_run=True)
            self.assertTrue(result["passed"])
            self.assertTrue(result["validator_passed"])
            self.assertTrue(result["requires_manual_review"])
            self.assertEqual(result["validator_mode"], "24h")
            self.assertNotIn("orders_count_expected_1", " ".join(result["errors"]))


class Stage3RunnerObserveTests(unittest.TestCase):
    @patch("tools.research.run_bybit_demo_learning_runner.time.sleep", return_value=None)
    @patch("tools.research.preflight_stage3_24h_runner.run_preflight", return_value={"preflight_passed": True})
    @patch("tools.research.run_bybit_demo_learning_runner.run_strict_env_gate", return_value={"strict_env_passed": True})
    @patch("tools.research.run_bybit_demo_learning_runner.demo_order_operator_go_present", return_value=True)
    @patch("tools.research.run_bybit_demo_learning_runner.operator_go_24h_present", return_value=True)
    @patch("tools.research.run_bybit_demo_learning_runner._is_24h_run", return_value=True)
    @patch("tools.research.run_bybit_demo_learning_runner.run_demo_order_micro_session")
    @patch("tools.research.run_bybit_demo_learning_runner.BybitDemoClient")
    def test_24h_observe_after_max_orders(
        self,
        mock_client_cls: MagicMock,
        mock_session: MagicMock,
        *_mocks: MagicMock,
    ) -> None:
        from tools.research.run_bybit_demo_learning_runner import run_loop

        mock_client = MagicMock()
        mock_client.mode = "demo-order"
        mock_client.count_open_positions.return_value = 0
        mock_client.fetch_ticker.return_value = {"lastPrice": 3200}
        mock_client.get_account_balance.return_value = {
            "snapshot_id": "snap",
            "balance_read_ok": True,
            "coin": "USDT",
            "total_equity": 1000,
            "wallet_balance": 1000,
            "available_balance": 1000,
            "max_allowed_margin": 50,
            "mainnet_detected": False,
            "real_money_detected": False,
        }
        mock_client_cls.return_value = mock_client
        mock_session.side_effect = [
            {"demo_order_sent": True, "position_closed": True, "open_positions_after": 0},
            {"demo_order_sent": True, "position_closed": True, "open_positions_after": 0},
        ]

        start = 1000.0
        end = start + 300.0
        clock = {"now": start}

        def fake_time() -> float:
            return clock["now"]

        def advance_sleep(_seconds: float) -> None:
            clock["now"] = min(clock["now"] + 60.0, end + 1.0)

        with patch("tools.research.run_bybit_demo_learning_runner.time.time", side_effect=fake_time):
            with patch("tools.research.run_bybit_demo_learning_runner.time.sleep", side_effect=advance_sleep):
                with patch.dict(
                    os.environ,
                    {
                        "OPERATOR_GO_STAGE3_24H_RUNNER": "true",
                        "NEXUS_KILL_SWITCH": "enabled",
                        "REQUIRE_STOP_LOSS": "true",
                        "REQUIRE_MAX_HOLD": "true",
                    },
                    clear=False,
                ):
                    audit = run_loop(
                        mode="demo-order",
                        duration_minutes=5.0,
                        poll_interval_seconds=1.0,
                        fresh_output=True,
                        max_orders=2,
                    )

        self.assertEqual(audit["orders_sent"], 2)
        self.assertEqual(mock_session.call_count, 2)
        self.assertGreaterEqual(audit.get("observe_ticks_after_orders_full", 0), 1)
        self.assertEqual(audit.get("runner_phase"), "OBSERVING_AFTER_MAX_ORDERS")
        self.assertTrue(audit.get("run_completed"))


class Stage3MockRepeatedMistakeTests(unittest.TestCase):
    def test_mock_scenario_blocks_second_entry(self) -> None:
        from tools.research.bybit_demo_client import BybitDemoClient
        from tools.research.run_bybit_demo_learning_runner import run_scenario_step
        from tools.research.stage3_learning_loop import Stage3LearningLoop

        with tempfile.TemporaryDirectory() as tmp:
            loop = Stage3LearningLoop(Path(tmp))
            client = BybitDemoClient("mock", allow_demo_order=False)
            snapshot = {
                "snapshot_id": "s1",
                "balance_read_ok": True,
                "total_equity": 1000,
                "available_balance": 1000,
                "max_allowed_margin": 50,
            }
            run_scenario_step(0, loop, client, snapshot, would_order=True)
            blocked = run_scenario_step(1, loop, client, snapshot, would_order=True)
            self.assertIsNotNone(blocked)
            self.assertGreater(loop.state.stats["repeated_mistake_blocked_count"], 0)


class Stage3ReadonlyWebTests(unittest.TestCase):
    def test_legacy_compat_endpoints(self) -> None:
        from tools.research.stage3_readonly_web_app import app

        client = app.test_client()
        for path in ("/api/nexus/state", "/api/nexus/status", "/api/nexus/snapshot"):
            resp = client.get(path)
            self.assertEqual(resp.status_code, 200, path)
            payload = resp.get_json()
            self.assertTrue(payload.get("read_only"))
            self.assertTrue(payload.get("legacy_compat"))
        post = client.post("/api/nexus/state", json={})
        self.assertEqual(post.status_code, 405)

        for path in ("/nexus", "/health", "/api/nexus/stage3/status"):
            resp = client.get(path)
            self.assertEqual(resp.status_code, 200, path)


if __name__ == "__main__":
    unittest.main()
