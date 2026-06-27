"""Stage 4 AI Decision Layer tests — dry-run only, no orders."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.research.stage4_ai_decision_agent import (
    REQUIRED_DECISION_FIELDS,
    Stage4AIDecisionAgent,
    Stage4PatchRetriever,
    resolve_stage4_output_dir,
    write_decision,
)
from tools.research.stage4_risk_supervisor import Stage4RiskSupervisor
from tools.research.stage3_learning_loop import append_jsonl


class Stage4SchemaTests(unittest.TestCase):
    def test_decision_schema_and_prompt_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agent = Stage4AIDecisionAgent()
            decision = agent.decide(
                symbol="ETHUSDT",
                mode="dry_run",
                market_context={"last_price": 3250, "prev_price_24h": 3200, "symbol": "ETHUSDT"},
                account_context={"available_balance": 5000, "balance_read_ok": True},
            )
            for fld in REQUIRED_DECISION_FIELDS:
                self.assertIn(fld, decision, fld)
            self.assertTrue(decision.get("prompt_hash"))
            self.assertFalse(decision.get("order_sent"))
            self.assertTrue(decision.get("is_mock_ai"))
            self.assertEqual(decision.get("model_name"), "mock_ai_decision_agent")


class Stage4RiskSupervisorTests(unittest.TestCase):
    def _proposal(self, **kwargs) -> dict:
        base = {
            "candidate_side": "BUY",
            "final_action": "enter",
            "confidence": 0.6,
            "position_size_suggestion": 15.0,
        }
        base.update(kwargs)
        return base

    def test_block_reentry_patch_veto(self) -> None:
        sup = Stage4RiskSupervisor()
        result = sup.evaluate(
            proposal=self._proposal(),
            account_context={"available_balance": 5000},
            retrieved_patches=[{"action": "block_reentry", "setup_key": "k1", "side": "BUY"}],
        )
        self.assertFalse(result.approved)
        self.assertEqual(result.final_decision, "skip")
        self.assertIn("block_reentry", result.veto_reason)

    def test_manual_review_required_veto(self) -> None:
        sup = Stage4RiskSupervisor()
        result = sup.evaluate(
            proposal=self._proposal(),
            account_context={"available_balance": 5000},
            retrieved_patches=[{"action": "manual_review_required", "setup_key": "k2"}],
        )
        self.assertFalse(result.approved)
        self.assertEqual(result.final_decision, "skip")

    def test_confidence_below_threshold_skip(self) -> None:
        sup = Stage4RiskSupervisor(confidence_threshold=0.5)
        result = sup.evaluate(
            proposal=self._proposal(confidence=0.2),
            account_context={"available_balance": 5000},
            retrieved_patches=[],
        )
        self.assertFalse(result.approved)
        self.assertEqual(result.action, "force_skip")

    def test_mainnet_hard_veto(self) -> None:
        sup = Stage4RiskSupervisor(
            constraints={
                "max_margin_usd": 20,
                "max_leverage": 3,
                "max_open_positions": 1,
                "require_stop_loss": True,
                "require_max_hold": True,
                "mainnet_allowed": True,
                "real_money": False,
                "production_promotion_allowed": False,
                "arm_allowed": False,
            }
        )
        result = sup.evaluate(
            proposal=self._proposal(),
            account_context={"available_balance": 5000},
            retrieved_patches=[],
        )
        self.assertEqual(result.veto_reason, "mainnet_allowed_true")

    def test_real_money_hard_veto(self) -> None:
        sup = Stage4RiskSupervisor(
            constraints={
                "max_margin_usd": 20,
                "max_leverage": 3,
                "max_open_positions": 1,
                "require_stop_loss": True,
                "require_max_hold": True,
                "mainnet_allowed": False,
                "real_money": True,
                "production_promotion_allowed": False,
                "arm_allowed": False,
            }
        )
        result = sup.evaluate(
            proposal=self._proposal(),
            account_context={"available_balance": 5000},
            retrieved_patches=[],
        )
        self.assertEqual(result.veto_reason, "real_money_true")

    def test_production_hard_veto(self) -> None:
        sup = Stage4RiskSupervisor(
            constraints={
                "max_margin_usd": 20,
                "max_leverage": 3,
                "max_open_positions": 1,
                "require_stop_loss": True,
                "require_max_hold": True,
                "mainnet_allowed": False,
                "real_money": False,
                "production_promotion_allowed": True,
                "arm_allowed": False,
            }
        )
        result = sup.evaluate(
            proposal=self._proposal(),
            account_context={"available_balance": 5000},
            retrieved_patches=[],
        )
        self.assertEqual(result.veto_reason, "production_promotion_allowed_true")


class Stage4PatchRetrievalTests(unittest.TestCase):
    def test_retrieved_patches_in_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stage3 = Path(tmp) / "stage3"
            stage3.mkdir()
            patch = {
                "patch_id": "p1",
                "symbol": "ETHUSDT",
                "side": "BUY",
                "action": "risk_reduce",
                "setup_key": "ETHUSDT|BUY|range|controlled_demo_order|controlled_demo_order",
            }
            append_jsonl(stage3 / "applied_learning_patches.jsonl", patch)
            agent = Stage4AIDecisionAgent(retriever=Stage4PatchRetriever(stage3_dir=stage3))
            decision = agent.decide(
                symbol="ETHUSDT",
                market_context={"last_price": 3250, "prev_price_24h": 3200},
                account_context={"available_balance": 5000},
            )
            self.assertGreaterEqual(len(decision.get("retrieved_patches") or []), 1)
            self.assertTrue(decision.get("patch_applied_before_decision"))


class Stage4DryRunIntegrationTests(unittest.TestCase):
    def test_fast_dry_run_all_order_sent_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            os.environ["STAGE4_OUTPUT_DIR"] = str(out)
            try:
                from tools.research.run_stage4_ai_decision_dry_run import run_dry_run

                with patch(
                    "tools.research.run_stage4_ai_decision_dry_run._fetch_market",
                    return_value={"last_price": 3250, "prev_price_24h": 3200, "symbol": "ETHUSDT"},
                ), patch(
                    "tools.research.run_stage4_ai_decision_dry_run._fetch_account",
                    return_value={"available_balance": 5000, "balance_read_ok": True, "open_positions": 0},
                ):
                    summary = run_dry_run(
                        duration_minutes=0.01,
                        poll_interval_seconds=0,
                        symbols=["ETHUSDT"],
                        output_dir=out,
                    )
                self.assertGreater(summary["decision_count"], 0)
                self.assertTrue(summary["all_order_sent_false"])
                from tools.research.validate_stage4_ai_decision_outputs import validate

                v = validate(out)
                self.assertTrue(v["passed"], v.get("errors"))
            finally:
                os.environ.pop("STAGE4_OUTPUT_DIR", None)


if __name__ == "__main__":
    unittest.main()
