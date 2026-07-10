"""Tests for Stage 4.18-P1B BTC shadow diagnostics."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_btc_shadow_diagnostics import analyze_btc_shadow_diagnostics
from tools.research.stage4_provider_routing_config import PROBE_RESULTS_JSONL, SHADOW_JSONL_FILENAME


class Stage418P1BShadowDiagnosticsTests(unittest.TestCase):
    def test_summarizes_shadow_jsonl_with_uncomparable(self) -> None:
        rows = [
            {
                "shadow_decision_id": "s1",
                "actual_provider": "cerebras",
                "shadow_provider": "groq",
                "actual_decision_intent": "soft_skip",
                "shadow_decision_intent": "not_called",
                "shadow_call_skipped": True,
                "shadow_skip_reason": "groq_tpm_cooldown_active",
                "shadow_would_be_valid_watch_under_current_rules": False,
                "provider_divergence_detected": False,
            },
            {
                "shadow_decision_id": "s2",
                "actual_provider": "groq",
                "shadow_provider": "cerebras",
                "actual_decision_intent": "soft_skip",
                "shadow_decision_intent": "soft_skip",
                "shadow_call_skipped": False,
                "shadow_would_be_valid_watch_under_current_rules": False,
                "provider_divergence_detected": False,
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / SHADOW_JSONL_FILENAME).write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            (root / "ai_decisions.jsonl").write_text("", encoding="utf-8")
            s = analyze_btc_shadow_diagnostics(input_dir=root, output_dir=root / "out")
            self.assertEqual(s["shadow_total_rows"], 2)
            self.assertEqual(s["shadow_call_skipped_count"], 1)
            self.assertEqual(s["shadow_comparable_pair_count"], 1)
            self.assertEqual(s["shadow_uncomparable_pair_count"], 1)
            self.assertFalse(s["provider_skill_comparison_valid"])
            self.assertFalse(s["p2_routing_experiment_recommended"])
            self.assertFalse(s["routing_change_supported"])
            self.assertIn("next_recommendation", s)
            self.assertTrue(s["shadow_excluded_from_paper_logger"])
            self.assertTrue(s["shadow_excluded_from_stage_419_readiness"])

    def test_reads_o3_probe_results_fallback(self) -> None:
        rows = [
            {
                "probe_id": "p1",
                "source_decision_id": "src1",
                "provider": "cerebras",
                "decision_intent": "watch",
                "confidence": 0.5,
                "would_be_valid_watch_under_current_rules": True,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / PROBE_RESULTS_JSONL).write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
            s = analyze_btc_shadow_diagnostics(input_dir=root, output_dir=root / "out")
            self.assertEqual(s["shadow_decision_count"], 1)

    def test_no_order_paths(self) -> None:
        import tools.research.stage4_btc_shadow_diagnostics as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("place_order", source)
        self.assertNotIn("btc-auto", source)


if __name__ == "__main__":
    unittest.main()
