"""Tests for Stage 4.18-P2F ETH watch reappearance gate."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_eth_watch_reappearance_gate import run_gate


class Stage418P2FReappearanceGateTests(unittest.TestCase):
    def _write_fixture(self, root: Path) -> dict[str, Path]:
        p2e = root / "p2e"
        p2b = root / "p2b"
        p2c = root / "p2c"
        p2d = root / "p2d"
        inp = root / "p2d_r1"
        out = root / "out"
        for d in (p2e, p2b, p2c, p2d, inp, out):
            d.mkdir()

        rows = [
            {
                "symbol": "ETHUSDT",
                "decision_id": f"eth-{i}",
                "decision_intent": intent,
                "provider": "groq",
                "confidence": conf,
                "candidate_side": "NONE",
                "directional_bias": "NONE",
                "entry_trigger": {"type": "none"},
                "invalidation": {},
                "mae_risk_estimate_pct": 0.0,
                "data_quality": "ok",
                "regime": "trend",
            }
            for i, (intent, conf) in enumerate(
                [
                    ("soft_skip", 0.2),
                    ("soft_skip", 0.25),
                    ("soft_skip", 0.3),
                    ("hard_skip", 0.2),
                    ("hard_skip", 0.1),
                ]
            )
        ]
        (inp / "ai_decisions.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
        )
        (p2e / "eth_no_watch_summary.json").write_text(
            json.dumps(
                {
                    "no_watch_root_cause": "sample_market_no_edge",
                    "eth_decision_count": 5,
                    "eth_intent_distribution": {"soft_skip": 3, "hard_skip": 2},
                    "eth_confidence_distribution": {"0.20_0.35": 4, "lt_0.20": 1},
                    "eth_directional_bias_distribution": {"NONE": 5},
                    "eth_candidate_side_distribution": {"NONE": 5},
                    "eth_block_reason_counts": {"skip_intent": 5},
                    "eth_valid_watch_count": 0,
                    "eth_entry_trigger_present_count": 0,
                    "eth_invalidation_present_count": 0,
                    "prompt_repair_over_conservative_suspected": False,
                    "needs_prompt_adjustment": False,
                    "p2b_eth_watch_reference": {
                        "provider": "cerebras",
                        "confidence": 0.55,
                        "directional_bias": "LONG",
                        "candidate_side": "BUY",
                        "mae_risk_estimate_pct": 0.3,
                    },
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
            json.dumps({"prompt_repair_added": True}),
            encoding="utf-8",
        )
        return {
            "p2e": p2e,
            "p2b": p2b,
            "p2c": p2c,
            "p2d": p2d,
            "input": inp,
            "output": out,
        }

    def test_negative_sample_blocks_regression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_fixture(Path(tmp))
            summary = run_gate(
                p2e_dir=paths["p2e"],
                p2b_dir=paths["p2b"],
                p2c_dir=paths["p2c"],
                p2d_dir=paths["p2d"],
                input_dir=paths["input"],
                output_dir=paths["output"],
            )
            self.assertTrue(summary["p2e_output_loaded"])
            self.assertTrue(summary["p2b_watch_reference_loaded"])
            self.assertTrue(summary["p2c_context_reference_loaded"])
            self.assertTrue(summary["p2d_prompt_repair_loaded"])
            ref = summary["reference_eth_watch"]
            self.assertEqual(ref["provider"], "cerebras")
            self.assertEqual(ref["intent"], "watch")
            self.assertEqual(ref["directional_bias"], "LONG")
            self.assertEqual(ref["candidate_side"], "BUY")
            self.assertFalse(summary["regression_readiness"])
            self.assertTrue(summary["do_not_run_regression_now"])
            self.assertFalse(summary["operator_approved_short_regression_may_be_justified"])
            self.assertFalse(summary["should_run_60m"])
            self.assertFalse(summary["stage_419_readiness"])
            self.assertFalse(summary["should_start_419"])
            self.assertEqual(
                summary["next_recommendation"],
                "wait_for_eth_watch_conditions_reappear_no_60m",
            )
            self.assertFalse(summary["order_sent"])
            self.assertFalse(summary["exchange_private_api_called"])
            blob = json.dumps(summary).lower()
            self.assertNotIn("btc-auto", blob)
            self.assertNotIn("/orders", blob)
            self.assertEqual(summary["p2f_verdict"], "STAGE_4_18P2F_PASS")
            self.assertTrue((paths["output"] / "eth_watch_reappearance_gate_summary.json").is_file())
            wait = summary["wait_helper_robustness_status"]
            self.assertEqual(wait.get("status"), "PASS")

    def test_ready_when_watch_conditions_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_fixture(Path(tmp))
            watch_row = {
                "symbol": "ETHUSDT",
                "decision_id": "eth-watch",
                "decision_intent": "watch",
                "provider": "cerebras",
                "confidence": 0.55,
                "candidate_side": "BUY",
                "directional_bias": "LONG",
                "entry_trigger": {
                    "type": "price_breakout",
                    "trigger_price": 3000.0,
                    "trigger_condition": "break above 3000",
                },
                "invalidation": {
                    "invalidation_price": 2900.0,
                    "invalidation_reason": "below structure",
                    "max_adverse_move_pct": 0.5,
                },
                "mae_risk_estimate_pct": 0.3,
                "data_quality": "ok",
                "regime": "trend",
                "edge_factors": ["momentum"],
                "risk_factors": [],
            }
            (paths["input"] / "ai_decisions.jsonl").write_text(
                json.dumps(watch_row) + "\n", encoding="utf-8"
            )
            summary = run_gate(
                p2e_dir=paths["p2e"],
                p2b_dir=paths["p2b"],
                p2c_dir=paths["p2c"],
                p2d_dir=paths["p2d"],
                input_dir=paths["input"],
                output_dir=paths["output"],
            )
            self.assertTrue(summary["regression_readiness"])
            self.assertFalse(summary["do_not_run_regression_now"])
            self.assertTrue(summary["operator_approved_short_regression_may_be_justified"])
            self.assertFalse(summary["should_run_60m"])
            self.assertFalse(summary["should_start_419"])
            self.assertEqual(
                summary["next_recommendation"],
                "operator_approved_short_runtime_regression_only",
            )


if __name__ == "__main__":
    unittest.main()
