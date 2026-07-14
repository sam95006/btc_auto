"""Tests for Stage 4.18-P2E ETH no-watch diagnostics."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_eth_no_watch_diagnostics import run_diagnostics


class Stage418P2ENoWatchTests(unittest.TestCase):
    def _write_fixture(self, root: Path) -> None:
        rows = [
            {
                "symbol": "ETHUSDT",
                "decision_id": f"eth-{i}",
                "decision_intent": intent,
                "provider": prov,
                "confidence": conf,
                "candidate_side": "NONE",
                "directional_bias": "NONE",
                "entry_trigger": {"type": "none"},
                "invalidation": {},
                "mae_risk_estimate_pct": 0.0,
                "why_skip": "no clear edge",
                "edge_factors": [],
                "risk_factors": ["chop"],
            }
            for i, (intent, prov, conf) in enumerate(
                [
                    ("soft_skip", "groq", 0.2),
                    ("soft_skip", "groq", 0.2),
                    ("soft_skip", "groq", 0.2),
                    ("hard_skip", "cerebras", 0.2),
                    ("hard_skip", "cerebras", 0.0),
                ]
            )
        ]
        (root / "ai_decisions.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
        )
        (root / "stage4_ai_decision_summary.json").write_text(
            json.dumps({"tick_count": 6, "effective_decision_count": 18}), encoding="utf-8"
        )

        analysis = root / "analysis"
        p2b = root / "p2b"
        p2c = root / "p2c"
        p2d = root / "p2d"
        for d in (analysis, p2b, p2c, p2d):
            d.mkdir()
        (analysis / "stage4_18p2d_r1_analysis_summary.json").write_text(
            json.dumps(
                {
                    "eth_actual_valid_watch_count": 0,
                    "eth_actual_graduation_count": 0,
                    "eth_followup_cases_count": 0,
                }
            ),
            encoding="utf-8",
        )
        (p2b / "eth_watch_confirmation_summary.json").write_text(
            json.dumps(
                {
                    "watch_provider": "cerebras",
                    "watch_confidence": 0.55,
                    "watch_directional_bias": "LONG",
                    "watch_candidate_side": "BUY",
                    "watch_mae_risk_estimate_pct": 0.3,
                }
            ),
            encoding="utf-8",
        )
        (p2c / "eth_followup_context_summary.json").write_text(
            json.dumps({"confirmation_failure_reason": "confirmation_prompt_too_strict"}),
            encoding="utf-8",
        )
        (p2d / "eth_followup_prompt_review_summary.json").write_text(
            json.dumps({"prompt_repair_added": True, "would_prevent_unexplained_collapse": True}),
            encoding="utf-8",
        )
        self.analysis = analysis
        self.p2b = p2b
        self.p2c = p2c
        self.p2d = p2d

    def test_no_watch_diagnostics(self) -> None:
        tool_src = (
            Path(__file__).resolve().parents[1]
            / "tools"
            / "research"
            / "stage4_eth_no_watch_diagnostics.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("place_order", tool_src)
        self.assertNotRegex(tool_src, r"\bbtc-auto\b")
        self.assertNotRegex(tool_src, r"/production\b")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            s = run_diagnostics(
                input_dir=root,
                output_dir=root / "out",
                analysis_dir=self.analysis,
                p2b_dir=self.p2b,
                p2c_dir=self.p2c,
                p2d_dir=self.p2d,
            )
            self.assertTrue(s["p2d_r1_output_loaded"])
            self.assertTrue(s["p2b_case_loaded"])
            self.assertTrue(s["p2c_case_loaded"])
            self.assertTrue(s["p2d_prompt_repair_loaded"])
            self.assertEqual(s["eth_valid_watch_count"], 0)
            self.assertEqual(s["eth_graduation_count"], 0)
            self.assertEqual(s["eth_decision_count"], 5)
            self.assertIn(s["no_watch_root_cause"], {
                "sample_market_no_edge",
                "prompt_repair_over_conservative",
                "confidence_below_watch_threshold",
                "entry_trigger_or_invalidation_missing",
                "provider_output_shift",
                "mae_above_cap",
            })
            self.assertFalse(s["should_run_60m"])
            self.assertFalse(s["stage_419_readiness"])
            self.assertFalse(s["should_start_419"])
            self.assertFalse(s["mae_cap_changed"])
            self.assertFalse(s["confidence_floor_changed"])
            self.assertFalse(s.get("needs_prompt_adjustment") and s["no_watch_root_cause"] == "sample_market_no_edge")
            # threshold change not recommended in sample_market_no_edge
            if s["no_watch_root_cause"] == "sample_market_no_edge":
                self.assertFalse(s["needs_prompt_adjustment"])
            self.assertEqual(s["p2e_verdict"], "STAGE_4_18P2E_PASS")
            self.assertTrue((root / "out" / "eth_no_watch_summary.json").is_file())


if __name__ == "__main__":
    unittest.main()
