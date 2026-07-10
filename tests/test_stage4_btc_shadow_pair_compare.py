"""Tests for Stage 4.18-P1A BTC shadow paired comparison export."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.research.stage4_btc_shadow_pair_compare import (
    build_summary,
    load_actual_btc_decisions,
    load_shadow_btc_decisions,
    pair_actual_and_shadow,
    run_pair_compare,
)
from tools.research.stage4_provider_routing_config import SHADOW_JSONL_FILENAME


def _actual(
    *,
    decision_id: str,
    intent: str = "soft_skip",
    provider: str = "cerebras",
    confidence: float = 0.2,
    side: str = "NONE",
    mae: float = 0.0,
    tick: int = 0,
) -> dict:
    row = {
        "decision_id": decision_id,
        "symbol": "BTCUSDT",
        "provider": provider,
        "decision_intent": intent,
        "confidence": confidence,
        "directional_bias": "NONE" if side == "NONE" else ("LONG" if side == "LONG" else "SHORT"),
        "candidate_side": side,
        "mae_risk_estimate_pct": mae,
        "tick_index": tick,
        "entry_trigger": {"type": "none", "trigger_condition": ""},
        "invalidation": {"invalidation_price": 0, "max_adverse_move_pct": 0},
        "parse_error": False,
    }
    if intent == "watch" and side != "NONE":
        row["entry_trigger"] = {
            "type": "price_breakout",
            "trigger_condition": "price breaks level",
        }
        row["invalidation"] = {
            "invalidation_price": 90000.0,
            "invalidation_reason": "below support",
            "max_adverse_move_pct": 0.28,
        }
        row["directional_bias"] = "LONG" if side == "LONG" else "SHORT"
        row["watch_confirmation_reason"] = "structure holds above support"
        row["paper_readiness"] = {
            "eligible_for_watchlist": True,
            "block_reason": "ok",
        }
    return row


def _shadow(
    *,
    source_decision_id: str,
    tick: int,
    actual_provider: str = "cerebras",
    shadow_provider: str = "groq",
    actual_intent: str = "soft_skip",
    shadow_intent: str = "unknown",
    valid: bool = False,
    divergence: bool = True,
    llm_error: str | None = None,
    side: str = "NONE",
    trigger: bool = False,
    inv: bool = False,
    mae: float | None = None,
) -> dict:
    return {
        "record_type": "btc_shadow_provider_decision",
        "shadow_decision_id": f"sh-{source_decision_id}",
        "source_decision_id": source_decision_id,
        "source_tick_index": tick,
        "symbol": "BTCUSDT",
        "actual_provider": actual_provider,
        "shadow_provider": shadow_provider,
        "actual_decision_intent": actual_intent,
        "shadow_decision_intent": shadow_intent,
        "shadow_confidence": 0.3,
        "shadow_directional_bias": "NONE",
        "shadow_candidate_side": side,
        "shadow_entry_trigger_present": trigger,
        "shadow_invalidation_present": inv,
        "shadow_mae_risk_estimate_pct": mae,
        "shadow_paper_readiness_eligible": False,
        "shadow_would_be_valid_watch_under_current_rules": valid,
        "provider_divergence_detected": divergence,
        "shadow_diagnostic_only": True,
        "llm_error": llm_error,
        "parse_error": bool(llm_error),
    }


class Stage418P1APairCompareTests(unittest.TestCase):
    def _write_fixture(self, root: Path) -> None:
        actuals = [
            _actual(decision_id="a0", intent="soft_skip", provider="cerebras", tick=0),
            _actual(
                decision_id="a1",
                intent="watch",
                provider="cerebras",
                confidence=0.55,
                side="LONG",
                mae=0.28,
                tick=1,
            ),
            _actual(decision_id="a2", intent="soft_skip", provider="groq", tick=2),
        ]
        shadows = [
            _shadow(
                source_decision_id="a0",
                tick=0,
                actual_provider="cerebras",
                shadow_provider="groq",
                actual_intent="soft_skip",
                shadow_intent="unknown",
            ),
            _shadow(
                source_decision_id="a1",
                tick=1,
                actual_provider="cerebras",
                shadow_provider="groq",
                actual_intent="watch",
                shadow_intent="unknown",
            ),
            _shadow(
                source_decision_id="a2",
                tick=2,
                actual_provider="groq",
                shadow_provider="cerebras",
                actual_intent="soft_skip",
                shadow_intent="soft_skip",
                divergence=False,
            ),
        ]
        (root / "ai_decisions.jsonl").write_text(
            "\n".join(json.dumps(r) for r in actuals) + "\n",
            encoding="utf-8",
        )
        (root / SHADOW_JSONL_FILENAME).write_text(
            "\n".join(json.dumps(r) for r in shadows) + "\n",
            encoding="utf-8",
        )
        (root / "stage4_ai_decision_summary.json").write_text(
            json.dumps({"btc_shadow_decision_count": 3}),
            encoding="utf-8",
        )

    def test_loads_and_pairs_by_source_decision_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            actuals = load_actual_btc_decisions(root)
            shadows = load_shadow_btc_decisions(root)
            self.assertEqual(len(actuals), 3)
            self.assertEqual(len(shadows), 3)
            pairs = pair_actual_and_shadow(actuals, shadows)
            self.assertEqual(len(pairs), 3)
            self.assertEqual(pairs[0][1]["decision_id"], "a0")
            self.assertEqual(pairs[0][2]["source_decision_id"], "a0")

    def test_summary_counts_and_unknown_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            summary = run_pair_compare(input_dir=root, output_dir=root / "out")
            self.assertEqual(summary["pair_count"], 3)
            self.assertEqual(summary["actual_valid_watch_count"], 1)
            self.assertEqual(summary["shadow_valid_watch_count"], 0)
            self.assertEqual(summary["divergence_count"], 2)
            self.assertEqual(summary["shadow_unknown_intent_count"], 2)
            self.assertIn("why_shadow_not_valid_watch_counts", summary)
            self.assertIn("why_actual_not_graduated_counts", summary)
            self.assertGreaterEqual(
                summary["why_shadow_not_valid_watch_counts"].get("shadow_unknown_intent", 0),
                1,
            )
            self.assertIn(
                "watchlist_followup_no_graduation",
                summary["why_actual_not_graduated_counts"],
            )
            self.assertFalse(summary["stage_419_readiness"])
            self.assertFalse(summary["routing_change_supported"])
            self.assertFalse(summary["p2_routing_experiment_recommended"])
            self.assertTrue((root / "out" / "paired_comparison.jsonl").is_file())
            self.assertTrue((root / "out" / "paired_comparison_summary.json").is_file())
            self.assertTrue((root / "out" / "paired_comparison_report.md").is_file())

    def test_pairs_by_tick_index_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actual = _actual(decision_id="x1", tick=5)
            shadow = _shadow(source_decision_id="", tick=5)
            shadow["source_decision_id"] = None
            (root / "ai_decisions.jsonl").write_text(json.dumps(actual) + "\n", encoding="utf-8")
            (root / SHADOW_JSONL_FILENAME).write_text(json.dumps(shadow) + "\n", encoding="utf-8")
            pairs = pair_actual_and_shadow(
                load_actual_btc_decisions(root),
                load_shadow_btc_decisions(root),
            )
            self.assertEqual(len(pairs), 1)
            self.assertEqual(pairs[0][0], 5)

    def test_does_not_call_llm_or_exchange(self) -> None:
        source = Path("tools/research/stage4_btc_shadow_pair_compare.py").read_text(
            encoding="utf-8"
        )
        for banned in (
            "Stage4LLMClient",
            "place_order",
            "btc-auto",
            "production_promotion",
            "create_order",
            "exchange private",
        ):
            self.assertNotIn(banned, source)

    def test_never_sets_stage_419_true(self) -> None:
        summary = build_summary([])
        self.assertFalse(summary["stage_419_readiness"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            s = run_pair_compare(input_dir=root, output_dir=root / "out")
            self.assertIs(s["stage_419_readiness"], False)

    def test_no_llm_invoked_during_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            with mock.patch("tools.research.stage4_llm_client.Stage4LLMClient", create=True) as llm:
                run_pair_compare(input_dir=root, output_dir=root / "out")
                llm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
