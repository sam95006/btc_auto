"""Tests for Stage 4.18-P1B BTC watchlist follow-up diagnostics."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_btc_watchlist_followup_diagnostics import analyze_btc_watchlist_followup


def _valid_btc_watch(decision_id: str = "btc-watch-1") -> dict:
    return {
        "decision_id": decision_id,
        "symbol": "BTCUSDT",
        "provider": "cerebras",
        "decision_intent": "watch",
        "confidence": 0.55,
        "directional_bias": "LONG",
        "candidate_side": "LONG",
        "mae_risk_estimate_pct": 0.28,
        "watch_confirmation_reason": "structure holds",
        "entry_trigger": {
            "type": "price_breakout",
            "trigger_condition": "break level",
        },
        "invalidation": {
            "invalidation_price": 90000.0,
            "invalidation_reason": "below support",
            "max_adverse_move_pct": 0.28,
        },
        "parse_error": False,
    }


class Stage418P1BWatchlistFollowupTests(unittest.TestCase):
    def test_detects_no_graduation_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decisions = [
                _valid_btc_watch("btc-1"),
                {
                    "decision_id": "btc-2",
                    "symbol": "BTCUSDT",
                    "decision_intent": "soft_skip",
                    "candidate_side": "NONE",
                    "directional_bias": "NONE",
                    "mae_risk_estimate_pct": 0,
                    "parse_error": False,
                },
            ]
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(d) for d in decisions) + "\n",
                encoding="utf-8",
            )
            paper = root / "paper"
            paper.mkdir()
            (paper / "events.jsonl").write_text(
                json.dumps(
                    {
                        "source_decision_id": "btc-1",
                        "symbol": "BTCUSDT",
                        "paper_action": "watchlist",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            cal = root / "cal"
            cal.mkdir()
            (cal / "calibration_replay_summary.json").write_text(
                json.dumps(
                    {
                        "mode_results": {
                            "major_mae_100": {
                                "mode": "major_mae_100",
                                "watchlist_created": 1,
                                "watchlist_confirmed": 0,
                                "hypothetical_graduation_count": 0,
                                "per_symbol_graduations": {},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            s = analyze_btc_watchlist_followup(
                input_dir=root,
                paper_events_dir=paper,
                calibration_dir=cal,
                output_dir=root / "out",
            )
            self.assertEqual(s["btc_actual_valid_watch_count"], 1)
            self.assertEqual(s["btc_graduation_count"], 0)
            self.assertFalse(s["stage_419_readiness"])
            self.assertIn(s["reason_no_graduation"], {
                "no_consecutive_confirmation",
                "watchlist_followup_no_graduation",
                "watchlist_opened_but_no_followup_tick",
                "watchlist_created_but_no_consecutive_confirmation",
            })
            self.assertTrue(s["offline_only"])
            self.assertFalse(s["order_sent"])
            self.assertFalse(s["llm_called"])

    def test_no_banned_paths(self) -> None:
        source = Path("tools/research/stage4_btc_watchlist_followup_diagnostics.py").read_text(
            encoding="utf-8"
        )
        for banned in ("place_order", "btc-auto", "production_promotion", "Stage4LLMClient"):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
