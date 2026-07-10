"""Tests for Stage 4.18-P2 provider routing design gate."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_provider_routing_p2_design import run_p2_design


class Stage418P2DesignTests(unittest.TestCase):
    def _write_p1c_fixture(self, root: Path) -> None:
        (root / "ai_decisions.jsonl").write_text("", encoding="utf-8")
        (root / "stage4_ai_decision_summary.json").write_text(
            json.dumps({"tick_count": 6, "effective_decision_count": 23}),
            encoding="utf-8",
        )
        pair = root / "pair"
        diag = root / "diag"
        follow = root / "follow"
        for d in (pair, diag, follow):
            d.mkdir()
        (pair / "paired_comparison_summary.json").write_text(
            json.dumps(
                {
                    "provider_skill_comparison_valid": True,
                    "actual_valid_watch_count": 0,
                    "shadow_valid_watch_count": 5,
                    "actual_provider_distribution": {"groq": 6},
                    "shadow_provider_distribution": {"cerebras": 6},
                    "shadow_comparable_pair_count": 5,
                    "shadow_uncomparable_pair_count": 1,
                    "shadow_excluded_from_graduation": True,
                    "shadow_excluded_from_paper_logger": True,
                    "shadow_excluded_from_calibration": True,
                    "shadow_excluded_from_stage_419_readiness": True,
                }
            ),
            encoding="utf-8",
        )
        (diag / "stage4_btc_shadow_diagnostics_summary.json").write_text(
            json.dumps(
                {
                    "provider_skill_comparison_valid": True,
                    "actual_valid_watch_count": 0,
                    "shadow_valid_watch_count": 5,
                    "shadow_excluded_from_graduation": True,
                }
            ),
            encoding="utf-8",
        )
        (follow / "stage4_btc_watchlist_followup_diagnostics.json").write_text(
            json.dumps({"reason_no_graduation": "no_btc_valid_watch"}),
            encoding="utf-8",
        )

    def test_design_from_p1c_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_p1c_fixture(root)
            s = run_p2_design(
                input_dir=root,
                pair_compare_dir=root / "pair",
                diagnostics_dir=root / "diag",
                followup_dir=root / "follow",
                output_dir=root / "out",
            )
            self.assertTrue(s["p1c_evidence_loaded"])
            self.assertTrue(s["provider_skill_comparison_valid"])
            self.assertTrue(s["shadow_excluded_from_graduation"])
            self.assertEqual(s["design_options_count"], 4)
            self.assertEqual(
                s["recommended_option"],
                "option_2_btc_cerebras_first_read_only_experiment",
            )
            self.assertTrue(s["operator_approval_required"])
            self.assertFalse(s["stage_419_readiness"])
            self.assertFalse(s["routing_auto_change_allowed"])
            self.assertTrue(s["provider_override_default_off"])
            self.assertTrue(s["provider_override_btc_only"])
            self.assertTrue(s["routing_experiment_design_supported"])
            self.assertTrue(s["p2_r1_experiment_defined"])
            self.assertFalse(s["execute_p2_r1_now"])
            self.assertEqual(s["actual_btc_valid_watch_count"], 0)
            self.assertEqual(s["shadow_btc_valid_watch_count"], 5)

    def test_no_banned_paths(self) -> None:
        source = Path("tools/research/stage4_provider_routing_p2_design.py").read_text(
            encoding="utf-8"
        )
        for banned in (
            "place_order",
            "create_order",
            "production_promotion",
            "NEXUS_ARM_ALLOWED\": \"true\"",
            "ZEABUR_PRODUCTION_RUNNER_ALLOWED\": \"true\"",
        ):
            self.assertNotIn(banned, source)
        self.assertIn("ARM/radar/production/btc-auto", source)
        self.assertIn('"NEXUS_ARM_ALLOWED": "false"', source)
        self.assertIn('"ZEABUR_PRODUCTION_RUNNER_ALLOWED": "false"', source)


if __name__ == "__main__":
    unittest.main()
