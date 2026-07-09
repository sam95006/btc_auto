"""Tests for Stage 4.18-O2 provider routing diagnostics."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_provider_routing_diagnostics import analyze_provider_routing_diagnostics


def _row(**overrides) -> dict:
    base = {
        "parse_error": False,
        "symbol": "BTCUSDT",
        "decision_intent": "soft_skip",
        "candidate_side": "NONE",
        "directional_bias": "NONE",
        "confidence": 0.2,
        "provider": "groq",
        "tick_index": 0,
        "fallback_used": False,
    }
    base.update(overrides)
    return base


def _eth_watch(**overrides) -> dict:
    base = {
        "parse_error": False,
        "symbol": "ETHUSDT",
        "decision_intent": "watch",
        "candidate_side": "BUY",
        "directional_bias": "LONG",
        "confidence": 0.55,
        "provider": "cerebras",
        "tick_index": 0,
        "fallback_used": True,
        "fallback_reason": "groq_rate_limited",
        "watch_confirmation_reason": "support",
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
    base.update(overrides)
    return base


class Stage418O2ProviderRoutingTests(unittest.TestCase):
    def test_counts_provider_by_symbol_and_intent(self) -> None:
        rows = [
            _row(decision_id="b1", tick_index=0),
            _row(decision_id="b2", tick_index=1),
            _eth_watch(decision_id="e1", tick_index=0),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            s = analyze_provider_routing_diagnostics(input_dir=root, output_dir=root / "out")
            self.assertEqual(s["provider_by_symbol"]["BTCUSDT"]["groq"], 2)
            self.assertEqual(s["provider_by_symbol"]["ETHUSDT"]["cerebras"], 1)
            self.assertEqual(s["provider_by_intent"]["soft_skip"]["groq"], 2)
            self.assertEqual(s["provider_by_intent"]["watch"]["cerebras"], 1)

    def test_counts_valid_watch_and_soft_skip_by_provider(self) -> None:
        rows = [_row(), _eth_watch(), _eth_watch(decision_id="e2", tick_index=1)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            s = analyze_provider_routing_diagnostics(input_dir=root, output_dir=root / "out")
            self.assertEqual(s["valid_watch_by_provider"].get("cerebras"), 2)
            self.assertEqual(s["valid_watch_by_provider"].get("groq", 0), 0)
            self.assertEqual(s["soft_skip_by_provider"].get("groq"), 1)

    def test_detects_btc_and_eth_provider_concentration(self) -> None:
        rows = [_row(tick_index=i) for i in range(4)] + [_eth_watch(tick_index=i) for i in range(2)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            s = analyze_provider_routing_diagnostics(input_dir=root, output_dir=root / "out")
            self.assertEqual(s["btc_provider_concentration"]["dominant_provider"], "groq")
            self.assertGreaterEqual(s["btc_provider_concentration"]["dominant_share"], 0.99)
            self.assertEqual(s["eth_provider_concentration"]["dominant_provider"], "cerebras")

    def test_detects_routing_asymmetry_and_recommendation(self) -> None:
        rows = [_row(tick_index=i) for i in range(3)] + [_eth_watch(tick_index=i) for i in range(2)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            s = analyze_provider_routing_diagnostics(input_dir=root, output_dir=root / "out")
            self.assertTrue(s["routing_asymmetry_detected"])
            self.assertTrue(s["routing_asymmetry_summary"])
            self.assertIn(
                s["recommendation"],
                {
                    "provider_routing_probe_recommended",
                    "cerebras_btc_probe_recommended",
                    "groq_btc_prompt_probe_recommended",
                },
            )
            self.assertIsNotNone(s.get("o3_controlled_probe_design"))

    def test_no_llm_or_order_paths(self) -> None:
        import tools.research.stage4_provider_routing_diagnostics as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("place_order", source)
        self.assertNotIn("Stage4LLMClient", source)
        self.assertNotIn("btc-auto", source)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ai_decisions.jsonl").write_text(json.dumps(_row()) + "\n", encoding="utf-8")
            s = analyze_provider_routing_diagnostics(input_dir=root)
            self.assertFalse(s["llm_providers_called"])
            self.assertFalse(s["order_sent"])
            self.assertFalse(s["production_touched"])
            self.assertFalse(s["btc_auto_touched"])


if __name__ == "__main__":
    unittest.main()
