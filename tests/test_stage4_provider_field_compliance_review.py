"""Tests for Stage 4.18-N provider field compliance review."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_provider_field_compliance_review import review_provider_field_compliance


class Stage418NProviderComplianceTests(unittest.TestCase):
    def test_review_groups_by_provider(self) -> None:
        rows = [
            {
                "decision_id": "g1",
                "parse_error": False,
                "provider": "groq",
                "symbol": "BTCUSDT",
                "decision_intent": "watch",
                "candidate_side": "NONE",
                "directional_bias": "LONG",
                "watch_confirmation_reason": "x",
                "mae_risk_estimate_pct": 1.5,
                "invalidation": {"invalidation_price": 99000, "max_adverse_move_pct": 0.30},
            },
            {
                "decision_id": "c1",
                "parse_error": False,
                "provider": "cerebras",
                "symbol": "ETHUSDT",
                "decision_intent": "watch",
                "candidate_side": "BUY",
                "directional_bias": "LONG",
                "watch_confirmation_reason": "x",
                "entry_trigger": {"type": "pullback_confirm", "trigger_price": 0, "trigger_condition": "x"},
                "invalidation": {"invalidation_price": 2991, "max_adverse_move_pct": 0.30},
                "mae_risk_estimate_pct": 0.30,
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            summary = review_provider_field_compliance(input_dir=root, output_dir=root / "out")
            self.assertIn("groq", summary["provider_stats"])
            self.assertIn("cerebras", summary["provider_stats"])
            self.assertIn("forbidden_repairs", summary["repair_policy"])
            self.assertTrue(summary["offline_only"])

    def test_no_order_or_exchange_paths(self) -> None:
        import tools.research.stage4_provider_field_compliance_review as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("place_order", source)
        self.assertNotIn("btc-auto", source)


if __name__ == "__main__":
    unittest.main()
