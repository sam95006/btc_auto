"""Tests for Stage 4.18-P2A ETH+BTC graduation alignment diagnostics."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_eth_btc_graduation_alignment_diagnostics import run_alignment


class Stage418P2AAlignmentTests(unittest.TestCase):
    def _write_fixture(self, root: Path) -> None:
        rows = [
            {
                "symbol": "BTCUSDT",
                "decision_id": "btc1",
                "decision_intent": "watch",
                "provider": "cerebras",
                "provider_chain": ["cerebras", "groq"],
                "confidence": 0.6,
                "candidate_side": "BUY",
                "entry_trigger": {"type": "breakout", "trigger_condition": "close>high"},
                "invalidation": {"invalidation_price": 1.0, "max_adverse_move_pct": 0.3},
                "mae_risk_estimate_pct": 0.3,
                "final_decision": "skip",
            },
            {
                "symbol": "ETHUSDT",
                "decision_id": "eth1",
                "decision_intent": "soft_skip",
                "provider": "groq",
                "provider_chain": ["groq", "cerebras"],
                "confidence": 0.2,
                "candidate_side": "NONE",
                "entry_trigger": {"type": "none", "trigger_condition": ""},
                "invalidation": {"invalidation_price": 0, "max_adverse_move_pct": 0},
                "mae_risk_estimate_pct": 0.0,
                "final_decision": "skip",
            },
            {
                "symbol": "ETHUSDT",
                "decision_id": "eth2",
                "decision_intent": "soft_skip",
                "provider": "cerebras",
                "provider_chain": ["groq", "cerebras"],
                "confidence": 0.0,
                "candidate_side": "NONE",
                "entry_trigger": {"type": "none"},
                "invalidation": {},
                "mae_risk_estimate_pct": 0.0,
                "final_decision": "skip",
            },
        ]
        (root / "ai_decisions.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
        )
        (root / "stage4_ai_decision_summary.json").write_text(
            json.dumps({"tick_count": 6, "effective_decision_count": 20, "parse_error_count": 0}),
            encoding="utf-8",
        )
        # Fake P2-R1 analysis path is absolute in tool; write local cal instead
        cal = root / "cal"
        cal.mkdir()
        (cal / "calibration_replay_summary.json").write_text(
            json.dumps(
                {
                    "mode_results": {
                        "major_mae_100": {
                            "mode": "major_mae_100",
                            "per_symbol_graduations": {"BTCUSDT": 3, "ETHUSDT": 0},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

    def test_alignment_from_p2_r1_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            s = run_alignment(
                input_dir=root,
                output_dir=root / "out",
                calibration_dir=root / "cal",
                paper_dir=root / "paper",
            )
            self.assertTrue(s["p2_r1_output_loaded"])
            self.assertGreaterEqual(s["btc_actual_graduation_count"], 1)
            self.assertEqual(s["eth_actual_graduation_count"], 0)
            self.assertFalse(s["stage_419_readiness"])
            self.assertFalse(s["should_start_419"])
            self.assertTrue(bool(s["eth_root_cause"]))
            self.assertFalse(s["shadow_used_for_graduation"])
            self.assertFalse(s["routing_permanent_change_supported"])
            self.assertFalse(s["should_run_60m"])
            self.assertEqual(s["eth_root_cause"], "eth_no_actual_valid_watch")

    def test_no_banned_paths(self) -> None:
        src = Path("tools/research/stage4_eth_btc_graduation_alignment_diagnostics.py").read_text(
            encoding="utf-8"
        )
        for banned in ("place_order", "create_order", "production_promotion"):
            self.assertNotIn(banned, src)
        self.assertIn("routing_permanent_change_supported", src)
        self.assertIn('"should_start_419": False', src) or self.assertIn(
            '"should_start_419": false', src.lower()
        )


if __name__ == "__main__":
    unittest.main()
