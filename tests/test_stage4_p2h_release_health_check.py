"""Tests for Stage 4.18-P2H-QA repository / release health check."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_p2h_release_health_check import (
    FUTURE_CHECKER,
    PLAN,
    RUNBOOK,
    UI_MVP10,
    run_release_health_check,
)


class Stage418P2HReleaseHealthCheckTests(unittest.TestCase):
    def test_runbook_exists(self) -> None:
        self.assertTrue(RUNBOOK.is_file(), "P2H operator hold runbook missing")

    def test_future_gate_checker_exists(self) -> None:
        self.assertTrue(FUTURE_CHECKER.is_file(), "future gate checker missing")

    def test_plan_contains_hold(self) -> None:
        text = PLAN.read_text(encoding="utf-8")
        self.assertIn("HOLD", text)
        self.assertTrue("p2h" in text.lower() or "4.18p2h" in text.lower())

    def test_ui_mvp10_report_exists(self) -> None:
        self.assertTrue(UI_MVP10.is_file(), "UI MVP-10 report missing")

    def test_release_health_summary_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_release_health_check(output_dir=tmp)
            self.assertTrue(summary["operator_runbook_exists"])
            self.assertTrue(summary["future_gate_checker_exists"])
            self.assertTrue(summary["plan_hold_state_consistent"])
            self.assertTrue(summary["ui_mvp10_report_exists"])
            self.assertTrue(summary["no_stage_419_start"])
            self.assertTrue(summary["no_order_path_added"])
            self.assertTrue(summary["no_arm_path_added"])
            self.assertTrue(summary["no_billing_or_accounts"])
            self.assertTrue(summary["release_checkpoint_ready"])
            self.assertEqual(summary["stage"], "4.18-P2H-QA")
            self.assertEqual(
                summary["next_recommendation"],
                "hold_backend_and_continue_private_operator_ui",
            )
            self.assertTrue((Path(tmp) / "p2h_release_health_summary.json").is_file())
            self.assertTrue((Path(tmp) / "p2h_release_health_report.md").is_file())
            self.assertFalse(summary.get("should_start_419", False))


if __name__ == "__main__":
    unittest.main()
