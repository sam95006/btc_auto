"""Tests for Stage 4.18-K/L paper entry failure analyzer."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_paper_entry_failure_analyzer import analyze_paper_entry_failures


def _valid_watch_row(**overrides) -> dict:
    row = {
        "decision_id": "d-valid",
        "parse_error": False,
        "symbol": "ETHUSDT",
        "decision_intent": "watch",
        "candidate_side": "BUY",
        "directional_bias": "LONG",
        "confidence": 0.5,
        "watch_confirmation_reason": "Support held",
        "entry_trigger": {
            "type": "pullback_confirm",
            "trigger_price": 3000,
            "trigger_condition": "Reclaim VWAP",
        },
        "invalidation": {
            "invalidation_price": 2991,
            "invalidation_reason": "break",
            "max_adverse_move_pct": 0.30,
        },
        "mae_risk_estimate_pct": 0.30,
    }
    row.update(overrides)
    return row


class Stage418KFailureAnalyzerTests(unittest.TestCase):
    def test_analyzer_counts_mae_above_cap(self) -> None:
        row = {
            "decision_id": "d1",
            "parse_error": False,
            "symbol": "ETHUSDT",
            "decision_intent": "watch",
            "candidate_side": "BUY",
            "directional_bias": "LONG",
            "confidence": 0.5,
            "watch_confirmation_reason": "x",
            "entry_trigger": {"type": "pullback_confirm", "trigger_price": 3000, "trigger_condition": "x"},
            "invalidation": {
                "invalidation_price": 2960,
                "invalidation_reason": "break",
                "max_adverse_move_pct": 1.33,
            },
            "mae_risk_estimate_pct": 1.33,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
            out = root / "out"
            summary = analyze_paper_entry_failures(input_dir=root, output_dir=out)
            self.assertEqual(summary["mae_above_symbol_cap_count"], 1)
            self.assertTrue(summary["offline_only"])
            self.assertFalse(summary["order_sent"])


class Stage418LFailureAnalyzerTests(unittest.TestCase):
    def test_analyzer_outputs_side_and_trigger_rates(self) -> None:
        rows = [
            _valid_watch_row(decision_id="v1"),
            {
                "decision_id": "bad-side",
                "parse_error": False,
                "symbol": "BTCUSDT",
                "decision_intent": "watch",
                "candidate_side": "NONE",
                "directional_bias": "SHORT",
                "watch_confirmation_reason": "x",
                "mae_risk_estimate_pct": 0.30,
                "invalidation": {"invalidation_price": 100300, "invalidation_reason": "x", "max_adverse_move_pct": 0.30},
            },
            {
                "decision_id": "bad-trigger",
                "parse_error": False,
                "symbol": "BTCUSDT",
                "decision_intent": "watch",
                "candidate_side": "SELL",
                "directional_bias": "SHORT",
                "watch_confirmation_reason": "x",
                "entry_trigger": {"type": "none", "trigger_price": 0, "trigger_condition": ""},
                "invalidation": {"invalidation_price": 100300, "invalidation_reason": "x", "max_adverse_move_pct": 0.30},
                "mae_risk_estimate_pct": 0.30,
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            summary = analyze_paper_entry_failures(input_dir=root, output_dir=root / "out")
            self.assertIn("candidate_side_missing_rate_by_symbol", summary)
            self.assertIn("missing_entry_trigger_rate_by_symbol", summary)
            self.assertIn("valid_watch_candidate_count_by_symbol", summary)
            self.assertEqual(summary["valid_watch_candidate_count_by_symbol"].get("ETHUSDT"), 1)
            self.assertTrue(summary["recommendations"])

    def test_analyzer_recommends_side_examples_when_high_missing(self) -> None:
        rows = [
            {
                "decision_id": f"s{i}",
                "parse_error": False,
                "symbol": "BTCUSDT",
                "decision_intent": "watch",
                "candidate_side": "NONE",
                "directional_bias": "LONG",
                "watch_confirmation_reason": "x",
                "mae_risk_estimate_pct": 0.30,
                "invalidation": {"invalidation_price": 1, "invalidation_reason": "x", "max_adverse_move_pct": 0.30},
            }
            for i in range(4)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            summary = analyze_paper_entry_failures(input_dir=root, output_dir=root / "out")
            joined = " ".join(summary["recommendations"])
            self.assertIn("structured_schema_side_required", joined)

    def test_analyzer_recommends_trigger_when_high_missing(self) -> None:
        rows = [
            {
                "decision_id": f"t{i}",
                "parse_error": False,
                "symbol": "ETHUSDT",
                "decision_intent": "watch",
                "candidate_side": "BUY",
                "directional_bias": "LONG",
                "watch_confirmation_reason": "x",
                "entry_trigger": {"type": "none", "trigger_price": 0, "trigger_condition": ""},
                "invalidation": {"invalidation_price": 2991, "invalidation_reason": "x", "max_adverse_move_pct": 0.30},
                "mae_risk_estimate_pct": 0.30,
            }
            for i in range(3)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            summary = analyze_paper_entry_failures(input_dir=root, output_dir=root / "out")
            joined = " ".join(summary["recommendations"])
            self.assertIn("structured_schema_trigger_required", joined)

    def test_no_order_or_exchange_in_analyzer(self) -> None:
        import tools.research.stage4_paper_entry_failure_analyzer as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("place_order", source)
        self.assertNotIn("btc-auto", source)


class Stage418MFailureAnalyzerTests(unittest.TestCase):
    def test_analyzer_outputs_mae_drift_and_field_contract(self) -> None:
        rows = [
            {
                "decision_id": "drift1",
                "parse_error": False,
                "symbol": "BTCUSDT",
                "decision_intent": "watch",
                "candidate_side": "NONE",
                "directional_bias": "LONG",
                "watch_confirmation_reason": "x",
                "entry_trigger": {"type": "none", "trigger_price": 0, "trigger_condition": ""},
                "invalidation": {"invalidation_price": 99000, "invalidation_reason": "x", "max_adverse_move_pct": 0.30},
                "mae_risk_estimate_pct": 1.5,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
            summary = analyze_paper_entry_failures(input_dir=root, output_dir=root / "out")
            self.assertIn("derived_candidate_side_suggestion_count", summary)
            self.assertIn("mae_scale_drift_suspected_count", summary)
            self.assertIn("field_contract_failure_by_symbol", summary)
            self.assertGreaterEqual(summary["derived_candidate_side_suggestion_count"], 1)
            self.assertGreaterEqual(summary["mae_scale_drift_suspected_count"], 1)
            self.assertIn("BTCUSDT", summary["field_contract_failure_by_symbol"])

    def test_analyzer_recommends_do_not_extend_sample(self) -> None:
        rows = [
            {
                "decision_id": f"w{i}",
                "parse_error": False,
                "symbol": "ETHUSDT",
                "decision_intent": "watch",
                "candidate_side": "NONE",
                "directional_bias": "LONG",
                "watch_confirmation_reason": "x",
                "mae_risk_estimate_pct": 1.5,
                "invalidation": {"invalidation_price": 2991, "invalidation_reason": "x", "max_adverse_move_pct": 0.30},
            }
            for i in range(3)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            summary = analyze_paper_entry_failures(input_dir=root, output_dir=root / "out")
            joined = " ".join(summary["recommendations"])
            self.assertIn("do_not_extend_sample_until_field_contract_passes", joined)


class Stage418NFailureAnalyzerTests(unittest.TestCase):
    def test_analyzer_reports_schema_repair_metrics(self) -> None:
        rows = [
            {
                "decision_id": "r1",
                "parse_error": False,
                "provider": "groq",
                "symbol": "BTCUSDT",
                "decision_intent": "watch",
                "candidate_side": " buy ",
                "directional_bias": "LONG",
                "entry_trigger": {"type": "pullback_confirm", "trigger_condition": "x"},
                "invalidation": {"invalidation_price": 99000, "max_adverse_move_pct": 0.3},
                "mae_risk_estimate_pct": 0.3,
                "watch_confirmation_reason": "x",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            summary = analyze_paper_entry_failures(input_dir=root, output_dir=root / "out")
            self.assertIn("schema_repair_applied_count", summary)
            self.assertIn("provider_side_missing_rate", summary)
            self.assertIn("groq", summary["provider_side_missing_rate"])


if __name__ == "__main__":
    unittest.main()
