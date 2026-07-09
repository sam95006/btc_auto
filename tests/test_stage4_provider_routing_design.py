"""Tests for Stage 4.18-P provider routing design gate."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_provider_routing_design import (
    O2_SUMMARY_NAME,
    O3_SUMMARY_NAME,
    REQUIRED_SAFEGUARDS,
    analyze_provider_routing_design,
)


def _o2_summary() -> dict:
    return {
        "routing_asymmetry_detected": True,
        "routing_asymmetry_likely_affected_btc": True,
        "routing_asymmetry_summary": "BTC 100% Groq",
        "valid_watch_by_provider": {"groq": 0, "cerebras": 6},
        "provider_by_symbol": {
            "BTCUSDT": {"groq": 12},
            "ETHUSDT": {"cerebras": 7},
        },
        "counterfactual_notes": {
            "btc_never_reached_cerebras": True,
            "cerebras_only_valid_watch_source": True,
        },
    }


def _o3_summary() -> dict:
    return {
        "provider_divergence_detected": True,
        "groq_valid_watch_count": 0,
        "cerebras_valid_watch_count": 1,
        "recommendation": "provider_routing_affects_btc_watch_yield",
    }


class Stage418PProviderRoutingDesignTests(unittest.TestCase):
    def _run(self, tmp: Path) -> dict:
        o2 = tmp / "o2"
        o3 = tmp / "o3"
        o2.mkdir()
        o3.mkdir()
        (o2 / O2_SUMMARY_NAME).write_text(json.dumps(_o2_summary()), encoding="utf-8")
        (o3 / O3_SUMMARY_NAME).write_text(json.dumps(_o3_summary()), encoding="utf-8")
        return analyze_provider_routing_design(
            o2_dir=o2,
            o3_dir=o3,
            output_dir=tmp / "out",
        )

    def test_reads_o2_and_o3_and_confirms_routing_problem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            s = self._run(Path(tmp))
            self.assertTrue(s["routing_problem_confirmed"])
            self.assertTrue(s["btc_never_reached_cerebras"])
            self.assertTrue(s["groq_zero_valid_watch_observed"])
            self.assertTrue(s["cerebras_only_valid_watch_source"])
            self.assertTrue(s["o3_provider_divergence_confirmed"])

    def test_outputs_four_design_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            s = self._run(Path(tmp))
            self.assertEqual(s["design_options_count"], 4)
            ids = {o["option_id"] for o in s["design_options"]}
            self.assertIn("option_1_status_quo", ids)
            self.assertIn("option_2_symbol_balanced_rotation", ids)
            self.assertIn("option_3_btc_dual_provider_shadow", ids)
            self.assertIn("option_4_cerebras_first_btc", ids)

    def test_recommends_diagnostic_shadow_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            s = self._run(Path(tmp))
            self.assertEqual(s["recommended_option"], "option_3_btc_dual_provider_shadow")
            self.assertTrue(s["p1_decision"]["should_implement_p1"])
            self.assertEqual(
                s["p1_decision"]["p1_scope"],
                "diagnostic-only BTC dual-provider shadow mode",
            )

    def test_operator_approval_and_no_419(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            s = self._run(Path(tmp))
            self.assertTrue(s["requires_operator_approval"])
            self.assertFalse(s["stage_419_readiness"])
            self.assertFalse(s["p1_decision"]["should_start_419"])
            self.assertFalse(s["p1_decision"]["should_run_soak_after_p1"])

    def test_shadow_exclusions_and_safeguards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            s = self._run(Path(tmp))
            self.assertTrue(s["shadow_excluded_from_paper_logger"])
            self.assertTrue(s["shadow_excluded_from_calibration"])
            self.assertTrue(s["shadow_excluded_from_graduation"])
            self.assertTrue(s["provider_routing_experiment_default_off"])
            self.assertGreaterEqual(len(s["required_safeguards"]), 8)
            for item in REQUIRED_SAFEGUARDS:
                self.assertIn(item, s["required_safeguards"])

    def test_no_order_or_production_paths(self) -> None:
        import tools.research.stage4_provider_routing_design as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("place_order", source)
        self.assertNotIn("btc-auto", source)
        self.assertNotIn("Stage4LLMClient", source)
        with tempfile.TemporaryDirectory() as tmp:
            s = self._run(Path(tmp))
            self.assertFalse(s["order_sent"])
            self.assertFalse(s["production_touched"])
            self.assertFalse(s["btc_auto_touched"])
            self.assertFalse(s["routing_changes_applied"])


if __name__ == "__main__":
    unittest.main()
