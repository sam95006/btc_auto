"""Tests for Stage 4.18-P2H passive ETH future regression gate checker."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_eth_future_regression_gate_checker import check_future_output


class Stage418P2HFutureGateCheckerTests(unittest.TestCase):
    def test_no_eth_watch_blocks_regression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            rows = [
                {
                    "symbol": "ETHUSDT",
                    "decision_id": f"eth-{i}",
                    "decision_intent": "soft_skip",
                    "provider": "groq",
                    "confidence": 0.2,
                    "candidate_side": "NONE",
                    "directional_bias": "NONE",
                    "entry_trigger": {"type": "none"},
                    "invalidation": {},
                    "mae_risk_estimate_pct": 0.0,
                    "data_quality": "ok",
                    "regime": "trend",
                }
                for i in range(3)
            ]
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
            )
            (root / "stage4_ai_decision_summary.json").write_text(
                json.dumps({"tick_count": 6, "effective_decision_count": 12}),
                encoding="utf-8",
            )
            summary = check_future_output(input_dir=root, output_dir=out)
            self.assertTrue(summary["future_output_loaded"])
            self.assertFalse(summary["eth_watch_conditions_reappeared"])
            self.assertFalse(summary["operator_approved_short_regression_may_be_justified"])
            self.assertFalse(summary["should_run_30m_now"])
            self.assertFalse(summary["should_run_60m"])
            self.assertFalse(summary["stage_419_readiness"])
            self.assertFalse(summary["should_start_419"])
            self.assertFalse(summary["auto_start_regression"])
            self.assertFalse(summary["auto_start_419"])
            self.assertEqual(summary["next_recommendation"], "continue_hold_no_regression")
            self.assertFalse(summary["order_sent"])
            blob = json.dumps(summary).lower()
            self.assertNotIn("btc-auto", blob)
            self.assertNotIn("/orders", blob)
            self.assertEqual(summary["p2h_verdict"], "STAGE_4_18P2H_PASS")

    def test_eth_watch_conditions_allow_operator_consideration_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            watch_row = {
                "symbol": "ETHUSDT",
                "decision_id": "eth-watch",
                "decision_intent": "watch",
                "provider": "cerebras",
                "confidence": 0.55,
                "candidate_side": "BUY",
                "directional_bias": "LONG",
                "entry_trigger": {
                    "type": "price_breakout",
                    "trigger_price": 3000.0,
                    "trigger_condition": "break above 3000",
                },
                "invalidation": {
                    "invalidation_price": 2900.0,
                    "invalidation_reason": "below structure",
                    "max_adverse_move_pct": 0.5,
                },
                "mae_risk_estimate_pct": 0.3,
                "data_quality": "ok",
                "regime": "trend",
            }
            (root / "ai_decisions.jsonl").write_text(
                json.dumps(watch_row) + "\n", encoding="utf-8"
            )
            (root / "stage4_ai_decision_summary.json").write_text(
                json.dumps({"tick_count": 6, "effective_decision_count": 18}),
                encoding="utf-8",
            )
            summary = check_future_output(input_dir=root, output_dir=out)
            self.assertTrue(summary["eth_watch_conditions_reappeared"])
            self.assertTrue(summary["operator_approved_short_regression_may_be_justified"])
            self.assertFalse(summary["should_run_30m_now"])
            self.assertFalse(summary["should_run_60m"])
            self.assertFalse(summary["should_start_419"])
            self.assertFalse(summary["auto_start_regression"])
            self.assertEqual(
                summary["next_recommendation"],
                "operator_may_approve_short_regression",
            )


if __name__ == "__main__":
    unittest.main()
