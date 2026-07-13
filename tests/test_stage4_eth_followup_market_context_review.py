"""Tests for Stage 4.18-P2C ETH follow-up market context review."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_eth_followup_market_context_review import run_review


class Stage418P2CContextReviewTests(unittest.TestCase):
    def _write_fixture(self, root: Path) -> None:
        rows = [
            {
                "symbol": "ETHUSDT",
                "decision_id": "eth-watch-1",
                "decision_intent": "watch",
                "provider": "cerebras",
                "confidence": 0.55,
                "candidate_side": "BUY",
                "directional_bias": "LONG",
                "entry_trigger": {"type": "breakout", "trigger_condition": "close>high"},
                "invalidation": {"invalidation_price": 3000.0, "max_adverse_move_pct": 0.3},
                "mae_risk_estimate_pct": 0.3,
                "market_context": {
                    "last_price": 3200.0,
                    "regime": "trend_up",
                    "trend_strength": 0.62,
                    "volatility": "medium",
                    "data_quality": "good",
                },
                "final_decision": "skip",
            },
            {
                "symbol": "ETHUSDT",
                "decision_id": "eth-follow-1",
                "decision_intent": "hard_skip",
                "provider": "cerebras",
                "confidence": 0.0,
                "candidate_side": "NONE",
                "directional_bias": "NONE",
                "entry_trigger": {"type": "none"},
                "invalidation": {},
                "mae_risk_estimate_pct": 0.0,
                "invalidation_hit": False,
                "market_context": {
                    "last_price": 3201.0,
                    "regime": "trend_up",
                    "trend_strength": 0.61,
                    "volatility": "medium",
                    "data_quality": "good",
                },
                "edge_factors": [],
                "risk_factors": [],
                "missing_data": [],
                "final_decision": "skip",
            },
            # BTC success pairs (3 watch→follow)
            {
                "symbol": "BTCUSDT",
                "decision_id": "btc-w1",
                "decision_intent": "watch",
                "provider": "cerebras",
                "confidence": 0.6,
                "candidate_side": "BUY",
                "directional_bias": "LONG",
                "entry_trigger": {"type": "breakout", "trigger_condition": "close>high"},
                "market_context": {
                    "last_price": 65000.0,
                    "regime": "trend_up",
                    "trend_strength": 0.7,
                    "volatility": "medium",
                    "data_quality": "good",
                },
            },
            {
                "symbol": "BTCUSDT",
                "decision_id": "btc-f1",
                "decision_intent": "watch",
                "provider": "cerebras",
                "confidence": 0.58,
                "candidate_side": "BUY",
                "directional_bias": "LONG",
                "entry_trigger": {"type": "breakout", "trigger_condition": "close>high"},
                "market_context": {
                    "last_price": 65050.0,
                    "regime": "trend_up",
                    "trend_strength": 0.68,
                    "volatility": "medium",
                    "data_quality": "good",
                },
            },
            {
                "symbol": "BTCUSDT",
                "decision_id": "btc-w2",
                "decision_intent": "watch",
                "provider": "cerebras",
                "confidence": 0.62,
                "candidate_side": "BUY",
                "directional_bias": "LONG",
                "entry_trigger": {"type": "breakout", "trigger_condition": "close>high"},
                "market_context": {
                    "last_price": 65100.0,
                    "regime": "trend_up",
                    "trend_strength": 0.71,
                    "volatility": "medium",
                    "data_quality": "good",
                },
            },
            {
                "symbol": "BTCUSDT",
                "decision_id": "btc-f2",
                "decision_intent": "watch",
                "provider": "cerebras",
                "confidence": 0.59,
                "candidate_side": "BUY",
                "directional_bias": "LONG",
                "entry_trigger": {"type": "breakout", "trigger_condition": "close>high"},
                "market_context": {
                    "last_price": 65120.0,
                    "regime": "trend_up",
                    "trend_strength": 0.7,
                    "volatility": "medium",
                    "data_quality": "good",
                },
            },
            {
                "symbol": "BTCUSDT",
                "decision_id": "btc-w3",
                "decision_intent": "watch",
                "provider": "cerebras",
                "confidence": 0.57,
                "candidate_side": "BUY",
                "directional_bias": "LONG",
                "entry_trigger": {"type": "breakout", "trigger_condition": "close>high"},
                "market_context": {
                    "last_price": 65200.0,
                    "regime": "trend_up",
                    "trend_strength": 0.65,
                    "volatility": "medium",
                    "data_quality": "good",
                },
            },
            {
                "symbol": "BTCUSDT",
                "decision_id": "btc-f3",
                "decision_intent": "watch",
                "provider": "cerebras",
                "confidence": 0.56,
                "candidate_side": "BUY",
                "directional_bias": "LONG",
                "entry_trigger": {"type": "breakout", "trigger_condition": "close>high"},
                "market_context": {
                    "last_price": 65210.0,
                    "regime": "trend_up",
                    "trend_strength": 0.64,
                    "volatility": "medium",
                    "data_quality": "good",
                },
            },
        ]
        (root / "ai_decisions.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
        )
        (root / "stage4_ai_decision_summary.json").write_text(
            json.dumps({"tick_count": 6, "effective_decision_count": 20}), encoding="utf-8"
        )

        p2b = root / "p2b"
        p2a = root / "p2a"
        p2b.mkdir()
        p2a.mkdir()
        (p2b / "eth_watch_confirmation_summary.json").write_text(
            json.dumps(
                {
                    "confirmation_failure_reason": "eth_followup_direction_changed",
                    "followup_invalidation_breached": False,
                    "followup_mae_breached": False,
                    "eth_valid_watch_count": 1,
                    "eth_graduation_count": 0,
                }
            ),
            encoding="utf-8",
        )
        (p2a / "eth_btc_alignment_summary.json").write_text(
            json.dumps({"eth_actual_valid_watch_count": 1, "btc_actual_graduation_count": 3}),
            encoding="utf-8",
        )
        self.p2b = p2b
        self.p2a = p2a

    def test_p2c_context_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            tool_src = (
                Path(__file__).resolve().parents[1]
                / "tools"
                / "research"
                / "stage4_eth_followup_market_context_review.py"
            ).read_text(encoding="utf-8")
            self.assertNotIn("place_order", tool_src)
            self.assertNotIn("submit_order", tool_src)
            self.assertNotRegex(tool_src, r"\bbtc-auto\b")
            self.assertNotRegex(tool_src, r"/production\b")

            s = run_review(
                input_dir=root,
                output_dir=root / "out",
                p2b_dir=self.p2b,
                p2a_dir=self.p2a,
            )
            self.assertTrue(s["p2_r1_output_loaded"])
            self.assertTrue(s["p2b_output_loaded"])
            self.assertEqual(s["eth_watch_tick_index"], 0)
            self.assertEqual(s["eth_followup_tick_index"], 1)
            self.assertIsNotNone(s["market_context_delta"])
            self.assertFalse(s["invalidation_breached"])
            self.assertFalse(s["mae_breached"])
            self.assertIn(
                s["confirmation_failure_reason"],
                {
                    "real_market_reversal_or_no_edge",
                    "followup_context_missing_or_degraded",
                    "confirmation_prompt_too_strict",
                    "provider_reasoning_collapse",
                    "risk_supervisor_over_block",
                    "entry_trigger_not_rechecked",
                    "insufficient_evidence_for_continuation",
                },
            )
            self.assertTrue(s["btc_success_context_comparison_loaded"])
            self.assertGreaterEqual(
                int((s.get("btc_success_context_patterns") or {}).get("count") or 0), 1
            )
            self.assertFalse(s["stage_419_readiness"])
            self.assertFalse(s["should_start_419"])
            self.assertFalse(s["should_run_60m"])
            self.assertFalse(s["routing_permanent_change_supported"])
            self.assertEqual(s["p2c_verdict"], "STAGE_4_18P2C_PASS")
            self.assertTrue((root / "out" / "eth_followup_context_summary.json").is_file())
            self.assertTrue((root / "out" / "eth_followup_context_details.jsonl").is_file())
            self.assertTrue((root / "out" / "eth_followup_context_report.md").is_file())


if __name__ == "__main__":
    unittest.main()
