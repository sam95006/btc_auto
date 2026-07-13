"""Tests for Stage 4.18-P2D ETH follow-up confirmation prompt review."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_eth_followup_confirmation_prompt_review import run_review
from tools.research.stage4_prompt_builder import (
    FOLLOWUP_CONFIRMATION_MARKERS,
    SYSTEM_PROMPT,
    build_decision_prompt,
)


class Stage418P2DPromptReviewTests(unittest.TestCase):
    def _write_p2c(self, root: Path) -> Path:
        p2c = root / "p2c"
        p2c.mkdir()
        (p2c / "eth_followup_context_summary.json").write_text(
            json.dumps(
                {
                    "stage": "4.18-P2C",
                    "confirmation_failure_reason": "confirmation_prompt_too_strict",
                    "invalidation_breached": False,
                    "mae_breached": False,
                    "watch_provider": "cerebras",
                    "watch_intent": "watch",
                    "watch_confidence": 0.55,
                    "watch_directional_bias": "LONG",
                    "watch_candidate_side": "BUY",
                    "watch_mae_risk_estimate_pct": 0.3,
                    "market_context_delta": {
                        "price_change_pct": -0.127,
                        "regime_before": "trend",
                        "regime_after": "trend",
                        "trend_strength_before": 0.41,
                        "trend_strength_after": 0.64,
                        "data_quality_before": "ok",
                        "data_quality_after": "ok",
                    },
                }
            ),
            encoding="utf-8",
        )
        return p2c

    def test_p2d_prompt_review(self) -> None:
        tool_src = (
            Path(__file__).resolve().parents[1]
            / "tools"
            / "research"
            / "stage4_eth_followup_confirmation_prompt_review.py"
        ).read_text(encoding="utf-8")
        prompt_src = (
            Path(__file__).resolve().parents[1]
            / "tools"
            / "research"
            / "stage4_prompt_builder.py"
        ).read_text(encoding="utf-8")
        agent_src = (
            Path(__file__).resolve().parents[1]
            / "tools"
            / "research"
            / "stage4_ai_decision_agent.py"
        ).read_text(encoding="utf-8")

        self.assertIn("previous_watch_rechecked", SYSTEM_PROMPT)
        self.assertIn("entry_trigger_rechecked", SYSTEM_PROMPT)
        self.assertIn("invalidation_status", SYSTEM_PROMPT)
        self.assertIn("mae_status", SYSTEM_PROMPT)
        self.assertTrue(any("NONE/NONE" in SYSTEM_PROMPT for _ in [1]))
        self.assertIn("direction_collapse_allowed", SYSTEM_PROMPT)
        self.assertIn("collapse_reason", SYSTEM_PROMPT)
        self.assertIn("previous_watch_context", prompt_src)
        self.assertIn("load_previous_watch_context_from_jsonl", agent_src)
        self.assertNotIn("place_order", tool_src)
        self.assertNotRegex(tool_src, r"\bbtc-auto\b")
        self.assertNotRegex(tool_src, r"/production\b")
        # No MAE / confidence floor / routing permanent changes in this repair
        self.assertNotIn("MAE_CAP", prompt_src.split("Follow-up confirmation")[-1][:800]
                         if "Follow-up confirmation" in prompt_src
                         else "")
        self.assertNotIn("CONFIDENCE_FLOOR", prompt_src)
        self.assertNotIn("STAGE4_PROVIDER_CHAIN", prompt_src.split("P2D")[-1] if "P2D" in prompt_src else "")

        msgs = build_decision_prompt(
            symbol="ETHUSDT",
            market_context={"last_price": 1.0, "regime": "trend", "data_quality": "ok"},
            account_context={},
            retrieved_patches=[],
            recent_trade_results=[],
            recent_reflections=[],
            safety_constraints={},
            current_open_positions=0,
            previous_watch_context={
                "symbol": "ETHUSDT",
                "decision_intent": "watch",
                "directional_bias": "LONG",
                "candidate_side": "BUY",
                "confidence": 0.55,
                "entry_trigger": {"type": "pullback_confirm", "trigger_condition": "x"},
                "invalidation": {"invalidation_price": 0.9},
                "mae_risk_estimate_pct": 0.3,
                "market_context": {"regime": "trend"},
            },
        )
        user = msgs[1]["content"]
        self.assertIn("previous_watch_context", user)
        self.assertIn("previous_watch_rechecked", user)
        self.assertIn("entry_trigger", user)
        self.assertIn("direction_collapse", user)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p2c = self._write_p2c(root)
            s = run_review(p2c_dir=p2c, input_dir=root, output_dir=root / "out")
            self.assertTrue(s["p2c_case_loaded"])
            self.assertTrue(s["prompt_repair_added"])
            self.assertTrue(s["previous_watch_recheck_required"])
            self.assertTrue(s["direction_collapse_guard_added"])
            self.assertTrue(s["confidence_collapse_reason_required"])
            self.assertTrue(s["would_prevent_unexplained_collapse"])
            self.assertEqual(
                s["static_expected_followup_behavior"],
                "continuation_watch_or_confirmation_pending",
            )
            self.assertFalse(s["mae_cap_changed"])
            self.assertFalse(s["confidence_floor_changed"])
            self.assertFalse(s["provider_routing_changed"])
            self.assertFalse(s["stage_419_readiness"])
            self.assertFalse(s["should_start_419"])
            self.assertFalse(s["should_run_60m"])
            self.assertFalse(s["should_run_30m_now"])
            self.assertTrue(s["needs_next_runtime_regression"])
            for m in ("previous_watch_rechecked", "entry_trigger_rechecked"):
                self.assertIn(m, FOLLOWUP_CONFIRMATION_MARKERS)


if __name__ == "__main__":
    unittest.main()
