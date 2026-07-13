"""Tests for Stage 4.18-P2B ETH watchlist confirmation diagnostics."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_eth_watchlist_confirmation_diagnostics import run_diagnostics


class Stage418P2BConfirmationTests(unittest.TestCase):
    def _write(self, root: Path) -> None:
        rows = [
            {
                "symbol": "ETHUSDT",
                "decision_id": "eth-watch-1",
                "decision_intent": "watch",
                "provider": "cerebras",
                "confidence": 0.55,
                "candidate_side": "BUY",
                "directional_bias": "BUY",
                "entry_trigger": {"type": "breakout", "trigger_condition": "close>high"},
                "invalidation": {"invalidation_price": 3000.0, "max_adverse_move_pct": 0.3},
                "mae_risk_estimate_pct": 0.3,
                "final_decision": "skip",
            },
            {
                "symbol": "ETHUSDT",
                "decision_id": "eth-follow-1",
                "decision_intent": "soft_skip",
                "provider": "cerebras",
                "confidence": 0.2,
                "candidate_side": "NONE",
                "directional_bias": "NONE",
                "entry_trigger": {"type": "none"},
                "invalidation": {},
                "mae_risk_estimate_pct": 0.0,
                "final_decision": "skip",
            },
            {
                "symbol": "BTCUSDT",
                "decision_id": "btc-w1",
                "decision_intent": "watch",
                "provider": "cerebras",
                "confidence": 0.6,
                "candidate_side": "BUY",
                "directional_bias": "BUY",
                "entry_trigger": {"type": "breakout", "trigger_condition": "close>high"},
                "invalidation": {"invalidation_price": 1.0, "max_adverse_move_pct": 0.3},
                "mae_risk_estimate_pct": 0.3,
                "final_decision": "skip",
            },
            {
                "symbol": "BTCUSDT",
                "decision_id": "btc-f1",
                "decision_intent": "watch",
                "provider": "cerebras",
                "confidence": 0.58,
                "candidate_side": "BUY",
                "entry_trigger": {"type": "breakout", "trigger_condition": "close>high"},
                "invalidation": {"invalidation_price": 1.0, "max_adverse_move_pct": 0.3},
                "mae_risk_estimate_pct": 0.29,
                "final_decision": "skip",
            },
        ]
        (root / "ai_decisions.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
        )
        (root / "stage4_ai_decision_summary.json").write_text(
            json.dumps({"tick_count": 6, "effective_decision_count": 20}), encoding="utf-8"
        )
        p2a = root / "p2a"
        analysis = root / "analysis"
        p2a.mkdir()
        analysis.mkdir()
        (p2a / "eth_btc_alignment_summary.json").write_text(
            json.dumps(
                {
                    "eth_actual_valid_watch_count": 1,
                    "eth_confirmation_failed_count": 1,
                    "eth_actual_graduation_count": 0,
                    "btc_actual_graduation_count": 3,
                    "eth_followup_tick_available_count": 1,
                }
            ),
            encoding="utf-8",
        )
        (analysis / "stage4_18p2_r1_analysis_summary.json").write_text(
            json.dumps({"btc_actual_graduation_count": 3, "eth_actual_graduation_count": 0}),
            encoding="utf-8",
        )
        self.p2a = p2a
        self.analysis = analysis

    def test_confirmation_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root)
            s = run_diagnostics(
                input_dir=root,
                output_dir=root / "out",
                p2a_dir=self.p2a,
                analysis_dir=self.analysis,
            )
            self.assertTrue(s["p2a_output_loaded"])
            self.assertTrue(s["p2_r1_output_loaded"])
            self.assertEqual(s["eth_valid_watch_count"], 1)
            self.assertEqual(s["eth_confirmation_failed_count"], 1)
            self.assertEqual(s["eth_graduation_count"], 0)
            self.assertTrue(bool(s["confirmation_failure_reason"]))
            self.assertTrue(s["btc_success_comparison_loaded"])
            self.assertFalse(s["stage_419_readiness"])
            self.assertFalse(s["should_start_419"])
            self.assertFalse(s["should_run_60m"])
            self.assertFalse(s["routing_permanent_change_supported"])
            self.assertIn(s["confirmation_failure_reason"], {
                "eth_followup_intent_not_watch",
                "eth_followup_direction_changed",
                "eth_provider_inconsistent",
                "eth_confidence_dropped",
            })

    def test_no_banned(self) -> None:
        src = Path("tools/research/stage4_eth_watchlist_confirmation_diagnostics.py").read_text(
            encoding="utf-8"
        )
        for banned in ("place_order", "create_order", "production_promotion"):
            self.assertNotIn(banned, src)


if __name__ == "__main__":
    unittest.main()
