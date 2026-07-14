"""Tests for Stage 4.18-P2G operator readiness pack."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_p2_operator_readiness_pack import run_pack


class Stage418P2GOperatorReadinessPackTests(unittest.TestCase):
    def _write(self, root: Path) -> dict[str, Path]:
        dirs = {
            "p2f": root / "p2f",
            "p2e": root / "p2e",
            "p2d": root / "p2d",
            "p2d_r1": root / "p2d_r1",
            "p2a": root / "p2a",
            "out": root / "out",
        }
        for d in dirs.values():
            d.mkdir()

        (dirs["p2f"] / "eth_watch_reappearance_gate_summary.json").write_text(
            json.dumps(
                {
                    "regression_readiness": False,
                    "do_not_run_regression_now": True,
                    "operator_approved_short_regression_may_be_justified": False,
                    "eth_watch_reappearance_conditions": {
                        "has_eth_watch_or_valid_watch": False,
                        "has_long_buy_bias": False,
                        "confidence_near_reference": False,
                        "entry_trigger_present": False,
                        "invalidation_present": False,
                        "mae_cap_passed": False,
                        "context_quality_ok": True,
                        "regime_not_unknown": True,
                    },
                    "wait_helper_robustness_status": {"status": "PASS"},
                    "p2d_prompt_repair_added": True,
                }
            ),
            encoding="utf-8",
        )
        (dirs["p2e"] / "eth_no_watch_summary.json").write_text(
            json.dumps(
                {
                    "no_watch_root_cause": "sample_market_no_edge",
                    "eth_valid_watch_count": 0,
                    "eth_graduation_count": 0,
                    "prompt_repair_over_conservative_suspected": False,
                }
            ),
            encoding="utf-8",
        )
        (dirs["p2d"] / "eth_followup_prompt_review_summary.json").write_text(
            json.dumps({"prompt_repair_added": True, "would_prevent_unexplained_collapse": True}),
            encoding="utf-8",
        )
        (dirs["p2d_r1"] / "stage4_18p2d_r1_analysis_summary.json").write_text(
            json.dumps(
                {
                    "btc_actual_graduation_count": 0,
                    "eth_actual_graduation_count": 0,
                    "eth_actual_valid_watch_count": 0,
                    "eth_confirmation_prompt_repair_effective": False,
                    "mock_ai_used_count": 0,
                    "order_sent_count": 0,
                    "technical_valid": True,
                }
            ),
            encoding="utf-8",
        )
        (dirs["p2a"] / "eth_btc_graduation_alignment_summary.json").write_text(
            json.dumps(
                {
                    "btc_actual_graduation_count": 3,
                    "eth_actual_graduation_count": 0,
                    "root_cause": "eth_followup_confirmation_failed",
                }
            ),
            encoding="utf-8",
        )
        return dirs

    def test_pack_blocks_regression_and_419(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write(Path(tmp))
            summary = run_pack(
                p2f_dir=paths["p2f"],
                p2e_dir=paths["p2e"],
                p2d_dir=paths["p2d"],
                p2d_r1_dir=paths["p2d_r1"],
                p2a_dir=paths["p2a"],
                output_dir=paths["out"],
            )
            self.assertTrue(summary["p2f_gate_loaded"])
            self.assertTrue(summary["p2e_no_watch_loaded"])
            self.assertTrue(summary["p2d_prompt_repair_loaded"])
            self.assertTrue(summary["eth_prompt_repair_done"])
            self.assertFalse(summary["eth_prompt_repair_runtime_validated"])
            self.assertFalse(summary["next_short_regression_allowed_now"])
            self.assertFalse(summary["should_run_60m"])
            self.assertFalse(summary["should_run_30m_now"])
            self.assertFalse(summary["stage_419_readiness"])
            self.assertFalse(summary["should_start_419"])
            self.assertFalse(summary["stage_419_dossier_allowed"])
            self.assertFalse(summary["routing_permanent_change_supported"])
            self.assertFalse(summary["order_sent"])
            blob = json.dumps(summary).lower()
            self.assertNotIn("btc-auto", blob)
            self.assertNotIn("/orders", blob)
            self.assertEqual(summary["p2g_verdict"], "STAGE_4_18P2G_PASS")
            self.assertTrue((paths["out"] / "p2_operator_readiness_summary.json").is_file())
            self.assertTrue(summary["btc_actual_graduation_evidence_exists"])
            self.assertEqual(summary["btc_latest_regression_graduation_count"], 0)


if __name__ == "__main__":
    unittest.main()
