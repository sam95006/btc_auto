"""Tests for Stage 4 cloud dry-run wait helper robustness."""
from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

from tools.research.wait_stage4_cloud_dry_run import (
    STATUS_COMPLETED_NEEDS_FINALIZE,
    STATUS_TIMEOUT,
    STATUS_WAITING,
    build_summary_poll_command,
    evaluate_wait_status,
    extract_json_object,
    wait_local,
)


class Stage4WaitHelperRobustnessTests(unittest.TestCase):
    def test_module_parses_without_syntax_error(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "tools"
            / "research"
            / "wait_stage4_cloud_dry_run.py"
        )
        src = path.read_text(encoding="utf-8")
        ast.parse(src)
        self.assertNotIn("place_order", src)
        self.assertNotIn("should_start_419=True", src)
        self.assertNotIn("start_stage_419", src.lower())

    def test_poll_command_builder_has_no_fstring_brace_bug(self) -> None:
        cmd = build_summary_poll_command("/data/stage4_ai_decisions_example")
        # Must be a valid python -c string fragment; compile the -c body
        self.assertIn("stage4_ai_decision_summary.json", cmd)
        body = cmd[len("python -c '") : -1]
        compile(body, "<poll>", "exec")

    def test_tick_reached_dry_run_false_returns_finalize_needed(self) -> None:
        result = evaluate_wait_status(
            snapshot={
                "tick_count": 6,
                "effective_decision_count": 18,
                "dry_run_completed": False,
                "cloud_dry_run_completed": False,
            },
            expected_tick_count=6,
            summary_present=True,
        )
        self.assertEqual(result["status"], STATUS_COMPLETED_NEEDS_FINALIZE)
        self.assertTrue(result["partial_completion_or_finalize_needed"])
        self.assertFalse(result["stage_419_triggered"])
        self.assertFalse(result["trading_state_mutated"])
        self.assertFalse(result["order_path_touched"])

    def test_timeout_when_ticks_not_reached(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "stage4_ai_decision_summary.json").write_text(
                json.dumps(
                    {
                        "tick_count": 2,
                        "effective_decision_count": 4,
                        "dry_run_completed": False,
                    }
                ),
                encoding="utf-8",
            )
            result = wait_local(
                output_dir=root,
                expected_tick_count=6,
                poll_seconds=0.01,
                max_polls=3,
            )
            self.assertEqual(result["status"], STATUS_TIMEOUT)
            self.assertFalse(result["stage_419_triggered"])
            self.assertFalse(result["trading_state_mutated"])

    def test_waiting_when_partial_ticks(self) -> None:
        result = evaluate_wait_status(
            snapshot={"tick_count": 3, "dry_run_completed": False},
            expected_tick_count=6,
            summary_present=True,
        )
        self.assertEqual(result["status"], STATUS_WAITING)

    def test_extract_json_ignores_npm_warn_noise(self) -> None:
        noisy = (
            '{"tick_count": 6, "dry_run_completed": false}\n'
            "npm warn Unknown env config \"devdir\".\n"
        )
        obj = extract_json_object(noisy)
        self.assertIsNotNone(obj)
        self.assertEqual(obj.get("tick_count"), 6)


if __name__ == "__main__":
    unittest.main()
