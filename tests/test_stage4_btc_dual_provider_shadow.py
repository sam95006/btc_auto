"""Tests for Stage 4.18-P1 BTC dual-provider shadow mode."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from tools.research.stage4_btc_dual_provider_shadow import (
    append_shadow_decision,
    build_shadow_row,
    maybe_run_and_write_btc_shadow,
    run_btc_shadow_for_actual,
    shadow_provider_for,
)
from tools.research.stage4_provider_routing_config import (
    ENV_BTC_DUAL_SHADOW,
    ENV_ROUTING_EXPERIMENT,
    is_btc_shadow_mode_active,
    is_shadow_decision_row,
    routing_config_summary,
    shadow_provider_for as config_shadow_for,
)


def _actual_btc(**overrides) -> dict:
    row = {
        "decision_id": "actual-btc-1",
        "symbol": "BTCUSDT",
        "provider": "groq",
        "decision_intent": "soft_skip",
        "confidence": 0.2,
        "directional_bias": "NONE",
        "candidate_side": "NONE",
        "parse_error": False,
        "market_context": {"symbol": "BTCUSDT", "regime": "trend", "last_price": 100000},
        "account_context": {},
        "retrieved_patches": [],
        "recent_trade_results": [],
        "recent_reflections": [],
        "stage3_context_summary": {"stage3_context_available": True},
    }
    row.update(overrides)
    return row


def _mock_llm(provider: str, messages, *, symbol: str, prompt_hash: str) -> dict:
    if provider == "groq":
        parsed = {
            "final_action": "skip",
            "symbol": symbol,
            "candidate_side": "NONE",
            "confidence": 0.2,
            "why_enter": "",
            "why_skip": "skip",
            "side_reason": "n",
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
            "confidence": 0.55,
            "why_enter": "edge",
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
    return {"status": "ok", "parsed": parsed, "provider": provider}


class Stage418P1ShadowTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop(ENV_ROUTING_EXPERIMENT, None)
        os.environ.pop(ENV_BTC_DUAL_SHADOW, None)

    def test_default_flags_shadow_inactive(self) -> None:
        os.environ.pop(ENV_ROUTING_EXPERIMENT, None)
        os.environ.pop(ENV_BTC_DUAL_SHADOW, None)
        cfg = routing_config_summary()
        self.assertFalse(cfg["provider_routing_experiment_enabled"])
        self.assertFalse(cfg["btc_dual_provider_shadow_enabled"])
        self.assertFalse(cfg["shadow_mode_active"])
        self.assertFalse(is_btc_shadow_mode_active())

    def test_only_routing_experiment_true_no_shadow(self) -> None:
        os.environ[ENV_ROUTING_EXPERIMENT] = "true"
        os.environ[ENV_BTC_DUAL_SHADOW] = "false"
        self.assertFalse(is_btc_shadow_mode_active())
        self.assertIsNone(run_btc_shadow_for_actual(actual_decision=_actual_btc(), tick_index=1))

    def test_both_flags_active(self) -> None:
        os.environ[ENV_ROUTING_EXPERIMENT] = "true"
        os.environ[ENV_BTC_DUAL_SHADOW] = "true"
        self.assertTrue(is_btc_shadow_mode_active())

    def test_only_btc_produces_shadow(self) -> None:
        os.environ[ENV_ROUTING_EXPERIMENT] = "true"
        os.environ[ENV_BTC_DUAL_SHADOW] = "true"
        eth = _actual_btc(symbol="ETHUSDT", provider="cerebras")
        self.assertIsNone(run_btc_shadow_for_actual(actual_decision=eth, tick_index=1, llm_fn=_mock_llm))
        row = run_btc_shadow_for_actual(actual_decision=_actual_btc(), tick_index=1, llm_fn=_mock_llm)
        self.assertIsNotNone(row)
        self.assertEqual(row["symbol"], "BTCUSDT")

    def test_shadow_provider_opposite(self) -> None:
        self.assertEqual(shadow_provider_for("groq"), "cerebras")
        self.assertEqual(shadow_provider_for("cerebras"), "groq")
        self.assertEqual(config_shadow_for("groq"), "cerebras")

    def test_shadow_row_flags_and_divergence(self) -> None:
        actual = _actual_btc()
        proposal = {
            "decision_intent": "watch",
            "candidate_side": "BUY",
            "directional_bias": "LONG",
            "confidence": 0.55,
            "entry_trigger": {
                "type": "pullback_confirm",
                "trigger_price": 100000,
                "trigger_condition": "x",
            },
            "invalidation": {
                "invalidation_price": 99000,
                "invalidation_reason": "break",
                "max_adverse_move_pct": 0.30,
            },
            "mae_risk_estimate_pct": 0.30,
            "watch_confirmation_reason": "ok",
        }
        row = build_shadow_row(
            actual_decision=actual,
            shadow_proposal=proposal,
            shadow_provider="cerebras",
            tick_index=2,
        )
        self.assertTrue(row["shadow_diagnostic_only"])
        self.assertTrue(row["provider_divergence_detected"])
        self.assertTrue(row["shadow_excluded_from_paper_logger"])
        self.assertTrue(row["shadow_excluded_from_calibration"])
        self.assertTrue(row["shadow_excluded_from_graduation"])
        self.assertTrue(row["shadow_excluded_from_stage_419_readiness"])
        self.assertFalse(row["order_sent"])

    def test_shadow_writes_separate_jsonl(self) -> None:
        os.environ[ENV_ROUTING_EXPERIMENT] = "true"
        os.environ[ENV_BTC_DUAL_SHADOW] = "true"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            actual = _actual_btc()
            row = maybe_run_and_write_btc_shadow(
                output_dir=out,
                actual_decision=actual,
                tick_index=1,
                llm_fn=_mock_llm,
            )
            self.assertIsNotNone(row)
            shadow_path = out / "btc_shadow_provider_decisions.jsonl"
            self.assertTrue(shadow_path.is_file())
            lines = shadow_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertNotIn("shadow_decision_id", (out / "ai_decisions.jsonl").read_text() if (out / "ai_decisions.jsonl").exists() else "")

    def test_shadow_row_detected_and_not_actual(self) -> None:
        self.assertTrue(is_shadow_decision_row({"shadow_diagnostic_only": True}))
        self.assertFalse(is_shadow_decision_row(_actual_btc()))


class Stage418P1ValidatorGuardTests(unittest.TestCase):
    def test_validator_fails_shadow_in_ai_decisions(self) -> None:
        from tools.research.validate_stage4_ai_decision_outputs import _validate_shadow_safety

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            technical: list[str] = []
            decisions = [{"shadow_diagnostic_only": True, "decision_id": "s1"}]
            _validate_shadow_safety(out=out, decisions=decisions, summary={}, technical_errors=technical)
            self.assertTrue(any("shadow_row_in_ai_decisions" in e for e in technical))

    def test_validator_fails_shadow_in_paper_events(self) -> None:
        from tools.research.validate_stage4_ai_decision_outputs import _validate_shadow_safety

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            sid = "shadow-abc"
            (out / "btc_shadow_provider_decisions.jsonl").write_text(
                json.dumps(
                    {
                        "shadow_decision_id": sid,
                        "shadow_excluded_from_paper_logger": True,
                        "shadow_excluded_from_calibration": True,
                        "shadow_excluded_from_graduation": True,
                        "shadow_excluded_from_stage_419_readiness": True,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (out / "hypothetical_entry_log.jsonl").write_text(
                json.dumps({"decision_id": sid}) + "\n",
                encoding="utf-8",
            )
            technical: list[str] = []
            _validate_shadow_safety(out=out, decisions=[], summary={}, technical_errors=technical)
            self.assertIn("shadow_decision_id_in_paper_events", technical)


if __name__ == "__main__":
    unittest.main()
