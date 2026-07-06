"""Tests for Stage 4.18-K paper entry failure analyzer."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_paper_entry_failure_analyzer import analyze_paper_entry_failures


class Stage418KFailureAnalyzerTests(unittest.TestCase):
    def test_analyzer_counts_mae_above_cap(self) -> None:
        row = {
            "decision_id": "d1",
            "parse_error": False,
            "symbol": "ETHUSDT",
            "decision_intent": "watch",
            "candidate_side": "BUY",
            "directional_bias": "LONG",
            "confidence": 0.5,
            "watch_confirmation_reason": "x",
            "entry_trigger": {"type": "pullback_confirm", "trigger_price": 3000, "trigger_condition": "x"},
            "invalidation": {
                "invalidation_price": 2960,
                "invalidation_reason": "break",
                "max_adverse_move_pct": 1.33,
            },
            "mae_risk_estimate_pct": 1.33,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
            out = root / "out"
            summary = analyze_paper_entry_failures(input_dir=root, output_dir=out)
            self.assertEqual(summary["mae_above_symbol_cap_count"], 1)
            self.assertTrue(summary["offline_only"])
            self.assertFalse(summary["order_sent"])


if __name__ == "__main__":
    unittest.main()
