"""Tests for Stage 4.18-O3 controlled provider probe."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_controlled_provider_probe import (
    build_context_record,
    run_controlled_provider_probe,
    select_btc_contexts,
)


def _btc_row(**overrides) -> dict:
    base = {
        "decision_id": "btc-1",
        "parse_error": False,
        "symbol": "BTCUSDT",
        "decision_intent": "soft_skip",
        "candidate_side": "NONE",
        "directional_bias": "NONE",
        "confidence": 0.20,
        "provider": "groq",
        "created_at_utc": "2026-07-09T00:00:00Z",
        "market_context": {"symbol": "BTCUSDT", "regime": "trend", "last_price": 100000},
        "account_context": {},
        "retrieved_patches": [],
        "recent_trade_results": [],
        "recent_reflections": [],
        "edge_factors": [],
        "risk_factors": ["unclear trend"],
        "stage3_context_summary": {"stage3_context_available": True, "stage3_context_reason": "ok"},
    }
    base.update(overrides)
    return base


def _eth_row(**overrides) -> dict:
    return _btc_row(
        decision_id="eth-1",
        symbol="ETHUSDT",
        decision_intent="watch",
        confidence=0.55,
        provider="cerebras",
        **overrides,
    )


def _mock_probe_fn(provider: str, messages, *, symbol: str, prompt_hash: str) -> dict:
    if provider == "groq":
        parsed = {
            "final_action": "skip",
            "symbol": symbol,
            "candidate_side": "NONE",
            "confidence": 0.2,
            "why_enter": "",
            "why_skip": "no edge",
            "side_reason": "none",
            "confidence_reason": "low",
            "risk_notes": [],
            "patch_awareness": "",
            "uncertainty": "high",
            "requires_manual_review": False,
            "decision_intent": "soft_skip",
            "directional_bias": "NONE",
        }
    else:
        parsed = {
            "final_action": "skip",
            "symbol": symbol,
            "candidate_side": "BUY",
            "confidence": 0.52,
            "why_enter": "trend",
            "why_skip": "",
            "side_reason": "long",
            "confidence_reason": "ok",
            "risk_notes": [],
            "patch_awareness": "",
            "uncertainty": "medium",
            "requires_manual_review": False,
            "decision_intent": "watch",
            "directional_bias": "LONG",
            "watch_confirmation_reason": "support",
            "entry_trigger": {
                "type": "pullback_confirm",
                "trigger_price": 100000,
                "trigger_condition": "reclaim",
            },
            "invalidation": {
                "invalidation_price": 99500,
                "invalidation_reason": "break",
                "max_adverse_move_pct": 0.30,
            },
            "mae_risk_estimate_pct": 0.30,
        }
    return {"status": "ok", "parsed": parsed, "provider": provider, "model": f"mock-{provider}"}


class Stage418O3ControlledProbeTests(unittest.TestCase):
    def test_selects_btc_contexts_not_eth(self) -> None:
        rows = [
            _btc_row(decision_id="b-low", confidence=0.20),
            _btc_row(decision_id="b-high", confidence=0.35),
            _btc_row(decision_id="b-recent", confidence=0.22, created_at_utc="2026-07-09T01:00:00Z"),
            _eth_row(),
        ]
        btc_only = [r for r in rows if str(r.get("symbol")).upper() == "BTCUSDT"]
        selected = select_btc_contexts(btc_only, max_contexts=3)
        self.assertEqual(len(selected), 3)
        self.assertTrue(all(str(r.get("symbol")).upper() == "BTCUSDT" for r in selected))

    def test_diagnostic_output_without_paper_or_calibration(self) -> None:
        rows = [_btc_row(decision_id=f"b{i}", confidence=0.20 + i * 0.05) for i in range(3)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            out = root / "probe_out"
            summary = run_controlled_provider_probe(
                input_dir=root,
                output_dir=out,
                dry_run_only=False,
                probe_fn=_mock_probe_fn,
            )
            self.assertFalse(summary["paper_events_written"])
            self.assertFalse(summary["calibration_written"])
            self.assertFalse(summary["ai_decisions_appended"])
            self.assertTrue((out / "stage4_controlled_provider_probe_results.jsonl").is_file())
            self.assertFalse((root / "ai_decisions.jsonl").read_text().count("probe_id"))

    def test_summary_counts_and_divergence(self) -> None:
        rows = [_btc_row(decision_id=f"b{i}", confidence=0.20 + i * 0.07) for i in range(3)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            summary = run_controlled_provider_probe(
                input_dir=root,
                output_dir=root / "out",
                dry_run_only=False,
                probe_fn=_mock_probe_fn,
            )
            self.assertEqual(summary["probe_context_count"], 3)
            self.assertEqual(summary["provider_probe_count"], 6)
            self.assertEqual(summary["groq_probe_count"], 3)
            self.assertEqual(summary["cerebras_probe_count"], 3)
            self.assertTrue(summary["provider_divergence_detected"])
            self.assertFalse(summary["stage_419_readiness"])

    def test_never_promotes_schema_repair_eligibility_in_probe(self) -> None:
        rows = [_btc_row()]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
            summary = run_controlled_provider_probe(
                input_dir=root,
                output_dir=root / "out",
                dry_run_only=False,
                probe_fn=_mock_probe_fn,
            )
            results = [
                json.loads(line)
                for line in (root / "out" / "stage4_controlled_provider_probe_results.jsonl").read_text().splitlines()
                if line.strip()
            ]
            self.assertTrue(all(not r.get("schema_repair_promoted_eligibility") for r in results))

    def test_no_order_exchange_production_paths(self) -> None:
        import tools.research.stage4_controlled_provider_probe as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("place_order", source)
        self.assertNotIn("bybit_demo_client", source)
        self.assertNotIn("btc-auto", source)
        self.assertNotIn("append_jsonl", source)
        rows = [_btc_row()]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
            summary = run_controlled_provider_probe(
                input_dir=root,
                dry_run_only=True,
            )
            self.assertFalse(summary["order_sent"])
            self.assertFalse(summary["exchange_private_api_called"])
            self.assertFalse(summary["production_touched"])
            self.assertFalse(summary["btc_auto_touched"])

    def test_context_record_preserves_frozen_fields(self) -> None:
        row = _btc_row()
        ctx = build_context_record(row)
        self.assertEqual(ctx["symbol"], "BTCUSDT")
        self.assertIn("market_context", ctx)
        self.assertEqual(ctx["original_decision"]["decision_intent"], "soft_skip")


if __name__ == "__main__":
    unittest.main()
