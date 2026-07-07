"""Tests for Stage 4.18-N safe schema repair."""
from __future__ import annotations

import unittest
from pathlib import Path

from tools.research.stage4_schema_repair import (
    FORBIDDEN_REPAIR_ACTIONS,
    apply_cosmetic_field_normalization,
    probe_schema_repair_on_decisions,
)


class Stage418NSchemaRepairTests(unittest.TestCase):
    def test_safe_repair_trims_strings(self) -> None:
        raw = {
            "candidate_side": " buy ",
            "directional_bias": " long ",
            "entry_trigger": {"type": " Pullback_Confirm ", "trigger_condition": " x "},
            "invalidation": {"invalidation_price": 1},
        }
        patched, meta = apply_cosmetic_field_normalization(raw)
        self.assertEqual(patched["candidate_side"], "BUY")
        self.assertEqual(patched["directional_bias"], "LONG")
        self.assertEqual(patched["entry_trigger"]["type"], "pullback_confirm")
        self.assertIn("trim_strings", meta["schema_repair_actions"])
        self.assertTrue(meta["schema_repair_safe_only"])

    def test_safe_repair_normalizes_candidate_side_casing(self) -> None:
        raw = {"candidate_side": "sell", "entry_trigger": {}, "invalidation": {}}
        patched, meta = apply_cosmetic_field_normalization(raw)
        self.assertEqual(patched["candidate_side"], "SELL")
        self.assertIn("normalize_candidate_side_casing", meta["schema_repair_actions"])

    def test_safe_repair_normalizes_directional_bias_casing(self) -> None:
        raw = {"directional_bias": "short", "entry_trigger": {}, "invalidation": {}}
        patched, meta = apply_cosmetic_field_normalization(raw)
        self.assertEqual(patched["directional_bias"], "SHORT")
        self.assertIn("normalize_directional_bias_casing", meta["schema_repair_actions"])

    def test_safe_repair_does_not_auto_set_candidate_side_from_bias(self) -> None:
        raw = {
            "decision_intent": "watch",
            "directional_bias": "LONG",
            "candidate_side": "NONE",
            "entry_trigger": {"type": "none", "trigger_condition": ""},
            "invalidation": {"invalidation_price": 100},
            "mae_risk_estimate_pct": 0.3,
        }
        patched, meta = apply_cosmetic_field_normalization(raw)
        self.assertEqual(patched["candidate_side"], "NONE")
        self.assertIn("auto_set_candidate_side_from_bias", meta["schema_repair_forbidden_actions_detected"])
        self.assertFalse(meta["schema_repair_safe_only"])

    def test_safe_repair_does_not_synthesize_entry_trigger(self) -> None:
        raw = {
            "decision_intent": "watch",
            "candidate_side": "BUY",
            "directional_bias": "LONG",
            "entry_trigger": {"type": "none", "trigger_condition": ""},
            "invalidation": {"invalidation_price": 100},
            "mae_risk_estimate_pct": 0.3,
        }
        _, meta = apply_cosmetic_field_normalization(raw)
        self.assertIn("synthesize_entry_trigger_to_pass", meta["schema_repair_forbidden_actions_detected"])

    def test_safe_repair_does_not_deflate_mae(self) -> None:
        raw = {
            "decision_intent": "watch",
            "candidate_side": "BUY",
            "directional_bias": "LONG",
            "entry_trigger": {"type": "pullback_confirm", "trigger_condition": "x"},
            "invalidation": {"max_adverse_move_pct": 0.2},
            "mae_risk_estimate_pct": 0.5,
        }
        patched, meta = apply_cosmetic_field_normalization(raw)
        self.assertEqual(patched["mae_risk_estimate_pct"], 0.5)
        self.assertIn("deflate_mae_to_pass_cap", meta["schema_repair_forbidden_actions_detected"])

    def test_safe_repair_does_not_promote_eligibility(self) -> None:
        raw = {
            "decision_intent": "watch",
            "symbol": "BTCUSDT",
            "candidate_side": "BUY",
            "directional_bias": "LONG",
            "entry_trigger": {"type": "pullback_confirm", "trigger_condition": "break"},
            "invalidation": {"invalidation_price": 99000, "max_adverse_move_pct": 0.3},
            "mae_risk_estimate_pct": 0.3,
            "watch_confirmation_reason": "ok",
        }
        _, meta = apply_cosmetic_field_normalization(raw)
        self.assertFalse(meta["schema_repair_promoted_eligibility"])

    def test_probe_aggregate_metrics(self) -> None:
        rows = [
            {
                "parse_error": False,
                "decision_intent": "watch",
                "directional_bias": "LONG",
                "candidate_side": "NONE",
                "entry_trigger": {"type": "none", "trigger_condition": ""},
                "invalidation": {},
            }
        ]
        summary = probe_schema_repair_on_decisions(rows)
        self.assertEqual(summary["schema_repair_applied_count"], 1)
        self.assertGreater(summary["schema_repair_forbidden_action_count"], 0)

    def test_no_order_or_exchange_paths(self) -> None:
        import tools.research.stage4_schema_repair as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("place_order", source)
        self.assertNotIn("btc-auto", source)
        self.assertNotIn("production", source.lower().split("forbidden")[0] if "forbidden" in source.lower() else source)

    def test_forbidden_actions_list_complete(self) -> None:
        self.assertIn("auto_set_candidate_side_from_bias", FORBIDDEN_REPAIR_ACTIONS)
        self.assertIn("synthesize_entry_trigger_to_pass", FORBIDDEN_REPAIR_ACTIONS)


if __name__ == "__main__":
    unittest.main()
