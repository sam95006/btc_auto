"""Tests for Stage 4.18-P2D-R1 analysis classifier helpers."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_p2d_r1_analysis import classify_verdict, run_analysis


class Stage418P2DR1AnalysisTests(unittest.TestCase):
    def test_classify_gate_candidate(self) -> None:
        v, n = classify_verdict(
            {
                "technical_valid": True,
                "btc_actual_graduation_count": 2,
                "eth_actual_graduation_count": 1,
                "eth_actual_valid_watch_count": 1,
                "eth_unexplained_direction_collapse_count": 0,
                "mock_ai_used_count": 0,
                "order_sent_count": 0,
            }
        )
        self.assertEqual(v, "STAGE_4_18P2D_R1_GATE_CANDIDATE")
        self.assertIn("4.19", n)

    def test_classify_repair_not_effective(self) -> None:
        v, _ = classify_verdict(
            {
                "technical_valid": True,
                "btc_actual_graduation_count": 1,
                "eth_actual_graduation_count": 0,
                "eth_actual_valid_watch_count": 1,
                "eth_unexplained_direction_collapse_count": 1,
                "mock_ai_used_count": 0,
                "order_sent_count": 0,
            }
        )
        self.assertEqual(v, "STAGE_4_18P2D_R1_FAIL_REPAIR_NOT_EFFECTIVE")

    def test_run_analysis_no_order_path(self) -> None:
        src = Path("tools/research/stage4_p2d_r1_analysis.py").read_text(encoding="utf-8")
        self.assertNotIn("place_order", src)
        self.assertNotRegex(src, r"\bbtc-auto\b")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                {
                    "symbol": "ETHUSDT",
                    "decision_intent": "watch",
                    "provider": "cerebras",
                    "confidence": 0.55,
                    "candidate_side": "BUY",
                    "directional_bias": "LONG",
                    "entry_trigger": {"type": "breakout", "trigger_condition": "x"},
                    "invalidation": {"invalidation_price": 1.0},
                    "mae_risk_estimate_pct": 0.3,
                    "market_context": {"last_price": 3000, "regime": "trend", "data_quality": "ok"},
                },
                {
                    "symbol": "ETHUSDT",
                    "decision_intent": "watch",
                    "provider": "cerebras",
                    "confidence": 0.5,
                    "candidate_side": "BUY",
                    "directional_bias": "LONG",
                    "entry_trigger": {"type": "breakout", "trigger_condition": "x"},
                    "invalidation": {"invalidation_price": 1.0},
                    "mae_risk_estimate_pct": 0.3,
                    "previous_watch_context_injected": True,
                    "previous_watch_rechecked": True,
                    "market_context": {
                        "last_price": 3001,
                        "regime": "trend",
                        "data_quality": "ok",
                    },
                },
            ]
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
            )
            (root / "stage4_ai_decision_summary.json").write_text(
                json.dumps(
                    {
                        "tick_count": 6,
                        "effective_decision_count": 20,
                        "parse_error_count": 0,
                        "mock_ai_used_count": 0,
                        "order_sent_count": 0,
                        "technical_valid": True,
                    }
                ),
                encoding="utf-8",
            )
            s = run_analysis(input_dir=root, output_dir=root / "out")
            self.assertEqual(s["stage"], "4.18-P2D-R1")
            self.assertEqual(s["eth_unexplained_direction_collapse_count"], 0)
            self.assertFalse(s["should_start_419"])
            self.assertFalse(s["stage_419_readiness"])


if __name__ == "__main__":
    unittest.main()
