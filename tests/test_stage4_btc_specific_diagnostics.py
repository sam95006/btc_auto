"""Tests for Stage 4.18-O BTC-specific diagnostics."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_btc_specific_diagnostics import analyze_btc_specific_diagnostics


def _btc_skip(**overrides) -> dict:
    row = {
        "decision_id": "btc-skip-1",
        "parse_error": False,
        "symbol": "BTCUSDT",
        "decision_intent": "soft_skip",
        "candidate_side": "NONE",
        "directional_bias": "NONE",
        "confidence": 0.25,
        "provider": "groq",
        "market_context": {"regime": "range"},
        "missing_data": ["volume"],
        "edge_factors": [],
        "risk_factors": ["low_liquidity"],
    }
    row.update(overrides)
    return row


def _btc_near_watch(**overrides) -> dict:
    row = {
        "decision_id": "btc-near-1",
        "parse_error": False,
        "symbol": "BTCUSDT",
        "decision_intent": "soft_skip",
        "candidate_side": "BUY",
        "directional_bias": "LONG",
        "confidence": 0.45,
        "provider": "groq",
        "market_context": {"regime": "trend"},
        "entry_trigger": {
            "type": "pullback_confirm",
            "trigger_price": 100000,
            "trigger_condition": "reclaim vwap",
        },
        "invalidation": {
            "invalidation_price": 99500,
            "invalidation_reason": "break",
            "max_adverse_move_pct": 0.30,
        },
        "mae_risk_estimate_pct": 0.30,
        "watch_confirmation_reason": "",
    }
    row.update(overrides)
    return row


def _eth_valid_watch(**overrides) -> dict:
    row = {
        "decision_id": "eth-valid-1",
        "parse_error": False,
        "symbol": "ETHUSDT",
        "decision_intent": "watch",
        "candidate_side": "BUY",
        "directional_bias": "LONG",
        "confidence": 0.55,
        "provider": "cerebras",
        "market_context": {"regime": "trend"},
        "watch_confirmation_reason": "support held",
        "entry_trigger": {
            "type": "pullback_confirm",
            "trigger_price": 3000,
            "trigger_condition": "reclaim",
        },
        "invalidation": {
            "invalidation_price": 2990,
            "invalidation_reason": "break",
            "max_adverse_move_pct": 0.30,
        },
        "mae_risk_estimate_pct": 0.30,
    }
    row.update(overrides)
    return row


class Stage418OBtcDiagnosticsTests(unittest.TestCase):
    def test_counts_btc_decisions_and_intents(self) -> None:
        rows = [
            _btc_skip(decision_id="b1"),
            _btc_skip(decision_id="b2", decision_intent="hard_skip"),
            _eth_valid_watch(),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            summary = analyze_btc_specific_diagnostics(input_dir=root, output_dir=root / "out")
            self.assertEqual(summary["btc_decision_count"], 2)
            self.assertEqual(summary["btc_valid_watch_count"], 0)
            self.assertEqual(summary["btc_soft_skip_count"], 1)
            self.assertEqual(summary["btc_hard_skip_count"], 1)
            self.assertEqual(summary["btc_watch_intent_count"], 0)

    def test_detects_near_watch_without_promotion(self) -> None:
        rows = [_btc_near_watch(), _eth_valid_watch()]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            summary = analyze_btc_specific_diagnostics(input_dir=root, output_dir=root / "out")
            self.assertGreaterEqual(summary["btc_near_watch_candidate_count"], 1)
            self.assertEqual(summary["btc_valid_watch_count"], 0)
            rows_out = list(
                (root / "out" / "stage4_btc_decision_rows.jsonl").read_text(encoding="utf-8").splitlines()
            )
            near_rows = [json.loads(l) for l in rows_out if json.loads(l).get("near_watch_candidate")]
            self.assertTrue(all(not r.get("valid_watch_candidate") for r in near_rows))

    def test_outputs_primary_cause_and_recommendation(self) -> None:
        rows = [_btc_skip() for _ in range(4)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            summary = analyze_btc_specific_diagnostics(input_dir=root, output_dir=root / "out")
            self.assertIn("btc_no_watch_primary_cause", summary)
            self.assertTrue(summary["btc_no_watch_primary_cause"])
            self.assertIn("btc_recommendation", summary)
            self.assertTrue(summary["btc_recommendation"])

    def test_outputs_btc_vs_eth_delta(self) -> None:
        rows = [_btc_skip(), _eth_valid_watch(), _eth_valid_watch(decision_id="eth-2")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            summary = analyze_btc_specific_diagnostics(input_dir=root, output_dir=root / "out")
            self.assertEqual(summary["eth_valid_watch_reference"]["count"], 2)
            self.assertIn("provider_gap", summary["btc_vs_eth_delta"])
            self.assertIn("confidence_gap", summary["btc_vs_eth_delta"])

    def test_handles_missing_paper_events_gracefully(self) -> None:
        rows = [_btc_skip()]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
            summary = analyze_btc_specific_diagnostics(
                input_dir=root,
                output_dir=root / "out",
                paper_events_dir=root / "missing_events",
                calibration_dir=root / "missing_cal",
                failure_analysis_dir=root / "missing_fail",
            )
            self.assertEqual(summary["btc_decision_count"], 1)
            self.assertTrue(summary["offline_only"])

    def test_no_order_or_exchange_paths(self) -> None:
        import tools.research.stage4_btc_specific_diagnostics as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("place_order", source)
        self.assertNotIn("exchange_private", source.lower().replace("exchange_private_api_called", ""))
        self.assertNotIn("btc-auto", source)
        self.assertFalse(summary := analyze_btc_specific_diagnostics.__doc__ and True)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(json.dumps(_btc_skip()) + "\n", encoding="utf-8")
            s = analyze_btc_specific_diagnostics(input_dir=root)
            self.assertFalse(s["order_sent"])
            self.assertFalse(s["exchange_private_api_called"])
            self.assertFalse(s["production_touched"])
            self.assertFalse(s["btc_auto_touched"])


if __name__ == "__main__":
    unittest.main()
