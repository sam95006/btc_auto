"""Stage 4 AI Decision Layer tests — dry-run only, no orders."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]

from tools.research.bybit_demo_client import BybitDemoClient
from tools.research.stage4_ai_decision_agent import (
    MOCK_MODEL_NAME,
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
            self.assertFalse(decision.get("real_llm_used"))
            self.assertEqual(decision.get("model_name"), "mock_ai_decision_agent")


class Stage4LLMSchemaTests(unittest.TestCase):
    def test_valid_llm_json_parse(self) -> None:
        from tools.research.stage4_decision_schema import parse_llm_decision

        raw = {
            "final_action": "skip",
            "symbol": "ETHUSDT",
            "candidate_side": "NONE",
            "confidence": 0.4,
            "why_enter": "",
            "why_skip": "No edge",
            "side_reason": "Flat",
            "confidence_reason": "Low conviction",
            "risk_notes": [],
            "patch_awareness": "",
            "uncertainty": "medium",
            "requires_manual_review": False,
        }
        proposal, ok, err = parse_llm_decision(raw, symbol="ETHUSDT")
        self.assertTrue(ok, err)
        self.assertEqual(proposal["final_action"], "skip")

    def test_malformed_llm_json_forces_skip(self) -> None:
        from tools.research.stage4_decision_schema import parse_llm_decision

        proposal, ok, err = parse_llm_decision({}, symbol="ETHUSDT")
        self.assertFalse(ok)
        self.assertEqual(proposal["final_action"], "skip")
        self.assertTrue(proposal.get("parse_error"))

    def test_agent_malformed_llm_response_skips(self) -> None:
        class FakeLLM:
            def availability(self):
                return {"real_llm_available": True, "model_name": "test-model"}

            def complete_json(self, messages, prompt_hash="", **kwargs):
                return {"status": "error", "parsed": {}, "error": "bad_json", "raw_text": "not json"}

        agent = Stage4AIDecisionAgent(use_real_llm=False, llm_client=FakeLLM())
        agent.real_llm_used = True
        agent.is_mock_ai = False
        agent.model_name = "test-model"
        agent.decision_source = "ai_decision_agent"
        decision = agent.decide(
            symbol="ETHUSDT",
            market_context={"last_price": 3250, "prev_price_24h": 3200},
            account_context={"available_balance": 5000},
        )
        self.assertFalse(decision.get("order_sent"))
        self.assertEqual(decision.get("final_decision"), "skip")
        self.assertTrue(decision.get("parse_error"))
        self.assertFalse(decision["risk_supervisor_result"]["approved"])

    def test_real_llm_unavailable_falls_back_to_mock(self) -> None:
        with patch(
            "tools.research.stage4_llm_client.Stage4LLMClient._resolve_config",
            return_value=None,
        ):
            agent = Stage4AIDecisionAgent(use_real_llm=True)
        self.assertTrue(agent.fallback_to_mock)
        self.assertTrue(agent.is_mock_ai)
        self.assertFalse(agent.real_llm_used)

    def test_mock_and_real_llm_flags_not_confused(self) -> None:
        mock_agent = Stage4AIDecisionAgent(use_real_llm=False)
        self.assertTrue(mock_agent.is_mock_ai)
        self.assertFalse(mock_agent.real_llm_used)
        decision = mock_agent.decide(
            symbol="ETHUSDT",
            market_context={"last_price": 3250, "prev_price_24h": 3200},
            account_context={"available_balance": 5000},
        )
        self.assertTrue(decision.get("is_mock_ai"))
        self.assertFalse(decision.get("real_llm_used"))
        self.assertFalse(decision.get("is_mock_ai") and decision.get("real_llm_used"))


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
        self.assertEqual(result.veto_reason, "patch_block")

    def test_manual_review_required_veto(self) -> None:
        sup = Stage4RiskSupervisor()
        result = sup.evaluate(
            proposal=self._proposal(),
            account_context={"available_balance": 5000},
            retrieved_patches=[{"action": "manual_review_required", "setup_key": "k2"}],
        )
        self.assertFalse(result.approved)
        self.assertEqual(result.final_decision, "skip")
        self.assertEqual(result.veto_reason, "manual_review_required")

    def test_confidence_below_threshold_skip(self) -> None:
        sup = Stage4RiskSupervisor(confidence_threshold=0.5)
        result = sup.evaluate(
            proposal=self._proposal(confidence=0.2),
            account_context={"available_balance": 5000},
            retrieved_patches=[],
            dry_run=False,
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

    def test_dry_run_log_path_auto_created(self) -> None:
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
                log_path = Path(summary["run_log_path"])
                self.assertTrue(log_path.is_file())
                text = log_path.read_text(encoding="utf-8")
                self.assertIn("START", text)
                self.assertIn("END", text)
            finally:
                os.environ.pop("STAGE4_OUTPUT_DIR", None)

    def test_output_dir_wires_llm_debug_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            from tools.research.run_stage4_ai_decision_dry_run import run_dry_run

            ok_payload = {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"final_action":"skip","symbol":"ETHUSDT","candidate_side":"NONE",'
                                '"confidence":0.0,"why_enter":"","why_skip":"wired debug test",'
                                '"side_reason":"","confidence_reason":"test","risk_notes":[],'
                                '"patch_awareness":"","uncertainty":"","requires_manual_review":false}'
                            )
                        },
                        "finish_reason": "stop",
                    }
                ]
            }
            with patch(
                "tools.research.run_stage4_ai_decision_dry_run._fetch_market",
                return_value={"last_price": 3250, "prev_price_24h": 3200, "symbol": "ETHUSDT"},
            ), patch(
                "tools.research.run_stage4_ai_decision_dry_run._fetch_account",
                return_value={"available_balance": 5000, "balance_read_ok": True, "open_positions": 0},
            ), patch(
                "tools.research.stage4_llm_client.Stage4LLMClient._http_post",
                return_value=(200, ok_payload),
            ), patch.dict(os.environ, {"GROQ_API_KEY_PRIMARY": "test-key-local-only"}, clear=False):
                from tools.research.stage4_rate_limit_gate import Stage4LLMRateGate

                Stage4LLMRateGate.reset_shared()
                os.environ.pop("STAGE4_OUTPUT_DIR", None)
                os.environ.pop("STAGE4_REQUIRE_STAGE3_CONTEXT", None)
                run_dry_run(
                    duration_minutes=0.01,
                    poll_interval_seconds=0,
                    symbols=["ETHUSDT"],
                    output_dir=out,
                    use_real_llm=True,
                )
            debug_path = out / "llm_client_debug.jsonl"
            self.assertTrue(debug_path.is_file(), "llm_client_debug.jsonl missing from --output-dir")
            debug_text = debug_path.read_text(encoding="utf-8")
            self.assertNotIn("test-key-local-only", debug_text)
            self.assertIn('"success": true', debug_text)
            self.assertFalse(os.environ.get("STAGE4_OUTPUT_DIR"), "env should be restored after run")


class Stage4ResponseParserTests(unittest.TestCase):
    def test_plain_json_parse_ok(self) -> None:
        from tools.research.stage4_response_parser import parse_llm_response_text

        parsed, ok, err = parse_llm_response_text('{"final_action":"skip","confidence":0.1}')
        self.assertTrue(ok, err)
        self.assertEqual(parsed["final_action"], "skip")

    def test_markdown_json_code_block_parse_ok(self) -> None:
        from tools.research.stage4_response_parser import parse_llm_response_text

        text = '```json\n{"final_action":"skip","candidate_side":"NONE","confidence":0.0}\n```'
        parsed, ok, err = parse_llm_response_text(text)
        self.assertTrue(ok, err)
        self.assertEqual(parsed["candidate_side"], "NONE")

    def test_malformed_json_skip(self) -> None:
        from tools.research.stage4_response_parser import parse_llm_response_text

        parsed, ok, err = parse_llm_response_text("not-json-at-all")
        self.assertFalse(ok)
        self.assertEqual(parsed, {})
        self.assertTrue(err)

    def test_missing_choices_path_empty(self) -> None:
        from tools.research.stage4_response_parser import extract_openai_compat_content

        content, path, finish = extract_openai_compat_content({"choices": []})
        self.assertEqual(content, "")
        self.assertEqual(path, "choices[missing]")
        self.assertIsNone(finish)


class Stage4LLMClientTests(unittest.TestCase):
    def test_groq_api_key_alias_resolves(self) -> None:
        from tools.research.stage4_llm_client import GROQ_KEY_ENVS, Stage4LLMClient

        env = {k: v for k, v in os.environ.items() if k not in GROQ_KEY_ENVS}
        env["GROQ_API_KEY"] = "cloud-test-key"
        with patch.dict(os.environ, env, clear=True):
            client = Stage4LLMClient(provider="groq", load_env=False)
        self.assertTrue(client.available)
        self.assertIn(client.config.api_key_env, ("GROQ_API_KEY", "GROQ_API_KEY_PRIMARY"))

    def test_empty_llm_response_skips(self) -> None:
        class EmptyLLM:
            def complete_json(self, messages, prompt_hash="", **kwargs):
                return {
                    "status": "error",
                    "error": "content_empty",
                    "error_type": "content_empty",
                    "parsed": {},
                    "raw_text": "",
                    "raw_content_empty": True,
                }

        agent = Stage4AIDecisionAgent(use_real_llm=False, llm_client=EmptyLLM())
        agent.real_llm_used = True
        agent.is_mock_ai = False
        agent.model_name = "test-model"
        agent.decision_source = "ai_decision_agent"
        from tools.research.stage4_llm_client import ProviderRateLimited

        with self.assertRaises(ProviderRateLimited):
            agent.decide(
                symbol="ETHUSDT",
                market_context={"last_price": 3250, "prev_price_24h": 3200},
                account_context={"available_balance": 5000},
            )

    def test_rate_limit_retry_then_skip(self) -> None:
        class FlakyLLM:
            def availability(self):
                return {"real_llm_available": True}

            def complete_json(self, messages, prompt_hash="", **kwargs):
                return {
                    "status": "error",
                    "error": "content_empty",
                    "error_type": "content_empty",
                    "parsed": {},
                    "raw_text": "",
                    "raw_content_empty": True,
                }

        agent = Stage4AIDecisionAgent(use_real_llm=False, llm_client=FlakyLLM())
        agent.real_llm_used = True
        agent.is_mock_ai = False
        agent.model_name = "test-model"
        agent.decision_source = "ai_decision_agent"
        from tools.research.stage4_llm_client import ProviderRateLimited

        with self.assertRaises(ProviderRateLimited):
            agent.decide(
                symbol="ETHUSDT",
                market_context={"last_price": 3250, "prev_price_24h": 3200},
                account_context={"available_balance": 5000},
            )

    def test_client_retries_rate_limit_then_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["STAGE4_OUTPUT_DIR"] = str(Path(tmp))
            try:
                from tools.research.stage4_llm_client import Stage4LLMClient, Stage4LLMConfig
                from tools.research.stage4_rate_limit_gate import Stage4LLMRateGate
                import urllib.error

                Stage4LLMRateGate.reset_shared()
                client = Stage4LLMClient(load_env=False)
                client.config = Stage4LLMConfig(
                    provider="groq",
                    model="llama-3.3-70b-versatile",
                    api_key_env="GROQ_API_KEY_PRIMARY",
                    endpoint="https://api.groq.com/openai/v1/chat/completions",
                )
                client.available = True
                calls = {"n": 0}

                def fake_post(url, headers, payload):
                    calls["n"] += 1
                    if calls["n"] == 1:
                        raise urllib.error.HTTPError(url, 503, "server", hdrs=None, fp=None)
                    return (
                        200,
                        {
                            "choices": [
                                {
                                    "message": {
                                        "content": '{"final_action":"skip","symbol":"ETHUSDT","candidate_side":"NONE","confidence":0.0,"why_enter":"","why_skip":"ok","side_reason":"","confidence_reason":"","risk_notes":[],"patch_awareness":"","uncertainty":"","requires_manual_review":false}'
                                    },
                                    "finish_reason": "stop",
                                }
                            ]
                        },
                    )

                with patch.object(client, "_http_post", side_effect=fake_post):
                    with patch.dict(os.environ, {"GROQ_API_KEY_PRIMARY": "test-key"}):
                        result = client.complete_json([{"role": "user", "content": "hi"}], prompt_hash="retry")
                self.assertEqual(result.get("status"), "ok")
                self.assertGreaterEqual(calls["n"], 2)
            finally:
                os.environ.pop("STAGE4_OUTPUT_DIR", None)

    def test_debug_log_excludes_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["STAGE4_OUTPUT_DIR"] = str(Path(tmp))
            try:
                from tools.research.stage4_llm_client import append_debug_log

                append_debug_log(
                    {
                        "error_message_safe": "Authorization Bearer sk-testsecret123456789",
                        "raw_content_excerpt": "api_key=supersecret",
                    }
                )
                log_path = Path(tmp) / "llm_client_debug.jsonl"
                text = log_path.read_text(encoding="utf-8")
                self.assertNotIn("sk-testsecret123456789", text)
                self.assertNotIn("supersecret", text)
                self.assertIn("[REDACTED]", text)
            finally:
                os.environ.pop("STAGE4_OUTPUT_DIR", None)

    def test_missing_choices_writes_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["STAGE4_OUTPUT_DIR"] = str(Path(tmp))
            try:
                from tools.research.stage4_llm_client import Stage4LLMClient, Stage4LLMConfig
                from tools.research.stage4_rate_limit_gate import Stage4LLMRateGate

                Stage4LLMRateGate.reset_shared()
                client = Stage4LLMClient(load_env=False)
                client.config = Stage4LLMConfig(
                    provider="groq",
                    model="llama-3.3-70b-versatile",
                    api_key_env="GROQ_API_KEY_PRIMARY",
                    endpoint="https://api.groq.com/openai/v1/chat/completions",
                )
                client.available = True
                client.timeout = 5
                client.max_tokens = 50
                with patch.object(client, "_http_post", return_value=(200, {"choices": []})):
                    result = client.complete_json([{"role": "user", "content": "hi"}], prompt_hash="abc")
                self.assertEqual(result.get("error_type"), "content_empty")
                log_text = (Path(tmp) / "llm_client_debug.jsonl").read_text(encoding="utf-8")
                self.assertIn("abc", log_text)
            finally:
                os.environ.pop("STAGE4_OUTPUT_DIR", None)


class Stage4RealLLMGuardTests(unittest.TestCase):
    def test_require_real_llm_missing_key_hard_fail_no_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            env = {
                "STAGE4_OUTPUT_DIR": str(out),
                "STAGE4_REQUIRE_REAL_LLM": "true",
                "STAGE4_ALLOW_MOCK_FALLBACK": "false",
            }
            env.update(
                {
                    k: v
                    for k, v in os.environ.items()
                    if k
                    not in (
                        "GROQ_API_KEY",
                        "GROQ_API_KEY_PRIMARY",
                        "GROQ_API_KEY_SECONDARY",
                        "CEREBRAS_API_KEY",
                        "OPENAI_API_KEY",
                        "ANTHROPIC_API_KEY",
                        "GOOGLE_API_KEY",
                    )
                }
            )
            with patch.dict(os.environ, env, clear=True), patch(
                "tools.research.stage4_llm_client._load_local_env"
            ):
                from tools.research.run_stage4_ai_decision_dry_run import run_dry_run

                summary = run_dry_run(
                    duration_minutes=0.01,
                    poll_interval_seconds=0,
                    symbols=["ETHUSDT"],
                    output_dir=out,
                    use_real_llm=True,
                )
            self.assertFalse(summary.get("dry_run_completed", True))
            self.assertEqual(summary.get("failed_reason"), "missing_real_llm_key")
            self.assertEqual(summary.get("decision_count"), 0)
            self.assertEqual(summary.get("order_sent_count"), 0)
            self.assertFalse((out / "ai_decisions.jsonl").is_file())

    def test_require_real_llm_disallows_mock_fallback_on_agent_init(self) -> None:
        with patch.dict(
            os.environ,
            {
                "STAGE4_REQUIRE_REAL_LLM": "true",
                "STAGE4_ALLOW_MOCK_FALLBACK": "false",
            },
            clear=False,
        ), patch(
            "tools.research.stage4_llm_client.Stage4LLMClient._resolve_config",
            return_value=None,
        ):
            from tools.research.stage4_llm_client import RealLLMRequiredError

            with self.assertRaises(RealLLMRequiredError):
                Stage4AIDecisionAgent(use_real_llm=True)

    def test_validator_require_real_llm_fails_on_mock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_decision(
                out,
                {
                    "decision_id": "d1",
                    "created_at_utc": "2026-01-01T00:00:00Z",
                    "decision_source": "mock_ai_decision_agent",
                    "mode": "dry_run",
                    "model_name": "mock_ai_decision_agent",
                    "is_mock_ai": True,
                    "real_llm_used": False,
                    "fallback_to_mock": True,
                    "prompt_hash": "abc",
                    "symbol": "ETHUSDT",
                    "candidate_side": "BUY",
                    "final_action": "skip",
                    "confidence": 0.1,
                    "position_size_suggestion": 0,
                    "market_context": {"symbol": "ETHUSDT"},
                    "account_context": {"available_balance": 5000},
                    "retrieved_patches": [],
                    "why_enter": "",
                    "why_skip": "test",
                    "side_reason": "test",
                    "confidence_reason": "test",
                    "risk_notes": [],
                    "safety_constraints": {},
                    "risk_supervisor_result": {"approved": False, "final_decision": "skip"},
                    "final_decision": "skip",
                    "order_sent": False,
                },
            )
            from tools.research.validate_stage4_ai_decision_outputs import validate

            result = validate(out, require_real_llm=True)
            self.assertFalse(result["passed"])
            self.assertIn("real_llm_used_count_zero", result["errors"])
            self.assertIn("mock_ai_used_count_gt_zero", result["errors"])
            self.assertEqual(result["order_sent_count"], 0)

    def test_validator_require_real_llm_fails_when_real_llm_used_count_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            from tools.research.validate_stage4_ai_decision_outputs import validate

            result = validate(out, require_real_llm=True)
            self.assertFalse(result["passed"])
            self.assertIn("real_llm_used_count_zero", result["errors"])

    def test_validator_require_real_llm_fails_when_debug_log_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "stage4_ai_decision_summary.json").write_text(
                json.dumps({"dry_run_completed": True, "real_llm_used_count": 1}),
                encoding="utf-8",
            )
            from tools.research.validate_stage4_ai_decision_outputs import validate

            result = validate(out, require_real_llm=True)
            self.assertFalse(result["passed"])
            self.assertIn("llm_client_debug_jsonl_missing", result["errors"])

    def test_require_real_llm_guard_keeps_order_sent_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "STAGE4_OUTPUT_DIR": str(out),
                    "STAGE4_REQUIRE_REAL_LLM": "true",
                    "STAGE4_ALLOW_MOCK_FALLBACK": "false",
                },
                clear=False,
            ), patch(
                "tools.research.stage4_llm_client.groq_key_configured",
                return_value=False,
            ):
                from tools.research.run_stage4_ai_decision_dry_run import run_dry_run

                summary = run_dry_run(
                    duration_minutes=0.01,
                    poll_interval_seconds=0,
                    symbols=["ETHUSDT"],
                    output_dir=out,
                    use_real_llm=True,
                )
            self.assertEqual(summary.get("order_sent_count"), 0)

    def test_health_check_uses_groq_primary_alias(self) -> None:
        from tools.research.check_stage4_llm_provider import run_health_check

        with patch.dict(os.environ, {"GROQ_API_KEY_PRIMARY": "alias-test-key"}, clear=False), patch(
            "tools.research.check_stage4_llm_provider.Stage4LLMClient"
        ) as mock_cls:
            mock_cls.return_value.availability.return_value = {
                "real_llm_available": True,
                "model_name": "llama-3.3-70b-versatile",
            }
            mock_cls.return_value.complete_json.return_value = {
                "status": "ok",
                "provider": "groq",
                "model": "llama-3.3-70b-versatile",
                "http_status": 200,
                "raw_content_length": 50,
                "parsed": {
                    "final_action": "skip",
                    "candidate_side": "NONE",
                    "confidence": 0.0,
                    "why_skip": "health_check",
                },
            }
            report = run_health_check(provider="groq", model="llama-3.3-70b-versatile")
        self.assertTrue(report.get("groq_key_present"))
        self.assertEqual(report.get("groq_key_env_used"), "GROQ_API_KEY_PRIMARY")


class Stage43MarketContextTests(unittest.TestCase):
    def test_btcusdt_read_only_ticker_allowed(self) -> None:
        client = BybitDemoClient("mock")
        ticker = client.fetch_ticker("BTCUSDT")
        self.assertEqual(ticker["symbol"], "BTCUSDT")

    def test_build_market_context_has_trend_volatility_regime(self) -> None:
        from tools.research.stage4_market_context import build_market_context

        ctx = build_market_context("ETHUSDT", client=BybitDemoClient("mock"))
        self.assertIn("change_24h_pct", ctx)
        self.assertIn("trend_15m", ctx)
        self.assertIn("volatility_15m", ctx)
        self.assertIn("regime", ctx)
        self.assertIn(ctx["data_quality"], {"ok", "partial", "error"})

    def test_missing_market_data_does_not_crash(self) -> None:
        from tools.research.stage4_market_context import build_market_context

        class BrokenClient(BybitDemoClient):
            def fetch_ticker(self, symbol: str = "ETHUSDT"):
                raise RuntimeError("ticker_down")

            def fetch_klines(self, symbol: str, **kwargs):
                raise RuntimeError("kline_down")

        ctx = build_market_context("BTCUSDT", client=BrokenClient("mock"))
        self.assertEqual(ctx["data_quality"], "error")
        self.assertTrue(ctx["data_limitations"])

    def test_stage3_context_summary_max_five(self) -> None:
        from tools.research.stage4_context_summary import summarize_trades

        rows = [{"symbol": "ETHUSDT", "side": "BUY", "close_pnl": -1} for _ in range(10)]
        self.assertEqual(len(summarize_trades(rows, limit=5)), 5)

    def test_prompt_includes_decision_intent_rules(self) -> None:
        from tools.research.stage4_prompt_builder import SYSTEM_PROMPT, OUTPUT_SCHEMA_HINT

        self.assertIn("decision_intent", SYSTEM_PROMPT)
        self.assertIn("hard_skip", OUTPUT_SCHEMA_HINT["decision_intent"])

    def test_parse_decision_intent_and_nonzero_soft_skip(self) -> None:
        from tools.research.stage4_decision_schema import parse_llm_decision

        raw = {
            "final_action": "skip",
            "symbol": "ETHUSDT",
            "candidate_side": "NONE",
            "confidence": 0.22,
            "decision_intent": "soft_skip",
            "why_enter": "",
            "why_skip": "Weak edge only",
            "side_reason": "Flat",
            "confidence_reason": "Some signal",
            "risk_notes": [],
            "patch_awareness": "",
            "uncertainty": "medium",
            "requires_manual_review": False,
        }
        proposal, ok, _ = parse_llm_decision(raw, symbol="ETHUSDT")
        self.assertTrue(ok)
        self.assertEqual(proposal["decision_intent"], "soft_skip")
        self.assertGreater(proposal["confidence"], 0.0)

    def test_supervisor_specific_veto_hard_skip(self) -> None:
        sup = Stage4RiskSupervisor()
        result = sup.evaluate(
            proposal={
                "final_action": "skip",
                "decision_intent": "hard_skip",
                "candidate_side": "NONE",
                "confidence": 0.05,
                "position_size_suggestion": 0,
            },
            account_context={"available_balance": 5000},
            retrieved_patches=[],
            market_context={"data_quality": "ok"},
        )
        self.assertEqual(result.veto_reason, "hard_skip")

    def test_dry_run_enter_veto_order_not_allowed(self) -> None:
        with patch.dict(os.environ, {"STAGE4_ORDER_ALLOWED": "false"}, clear=False):
            sup = Stage4RiskSupervisor()
            result = sup.evaluate(
                proposal={
                    "final_action": "enter",
                    "decision_intent": "enter_candidate",
                    "candidate_side": "BUY",
                    "confidence": 0.7,
                    "position_size_suggestion": 10,
                },
                account_context={"available_balance": 5000},
                retrieved_patches=[],
                market_context={"data_quality": "ok"},
                dry_run=True,
            )
        self.assertEqual(result.veto_reason, "order_not_allowed_dry_run")
        self.assertFalse(result.approved)


class Stage44RegimeContextTests(unittest.TestCase):
    def test_regime_classification_trend_from_mock_klines(self) -> None:
        from tools.research.stage4_market_context import build_market_context, classify_regime_from_klines

        closes = [100.0 + i * 0.8 for i in range(20)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        info = classify_regime_from_klines(closes, highs, lows, change_24h_pct=0.5)
        self.assertIn(info["regime"], {"trend", "volatile", "range"})
        self.assertIn("regime_reason", info)
        self.assertIn(info["volatility_level"], {"low", "medium", "high", "unknown"})

        ctx = build_market_context("ETHUSDT", client=BybitDemoClient("mock"))
        self.assertIn("regime_reason", ctx)
        self.assertIn("trend_strength", ctx)
        self.assertIn("volatility_level", ctx)
        self.assertIn("kline_data_quality", ctx)
        self.assertNotEqual(ctx["regime"], "unknown")

    def test_missing_kline_does_not_crash(self) -> None:
        from tools.research.stage4_market_context import classify_regime_from_klines

        info = classify_regime_from_klines([], [], [])
        self.assertEqual(info["regime"], "unknown")
        self.assertEqual(info["kline_data_quality"], "error")

    def test_stage3_context_files_missing_no_crash(self) -> None:
        from tools.research.stage4_context_summary import load_stage3_context

        with tempfile.TemporaryDirectory() as tmp:
            ctx = load_stage3_context(Path(tmp), symbol="ETHUSDT")
        self.assertFalse(ctx["stage3_context_available"])
        self.assertEqual(ctx["stage3_context_reason"], "files_missing")
        self.assertEqual(ctx["recent_trade_results_count"], 0)

    def test_stage3_context_max_five(self) -> None:
        from tools.research.stage4_context_summary import load_stage3_context

        with tempfile.TemporaryDirectory() as tmp:
            stage3 = Path(tmp)
            trades = stage3 / "trade_results.jsonl"
            for i in range(8):
                append_jsonl(
                    trades,
                    {"symbol": "ETHUSDT", "side": "BUY", "close_pnl": -0.1 * i, "created_at_utc": f"t{i}"},
                )
            ctx = load_stage3_context(stage3, symbol="ETHUSDT", trade_limit=5)
        self.assertTrue(ctx["stage3_context_available"])
        self.assertEqual(len(ctx["recent_trade_results"]), 5)

    def test_patch_block_separated_from_hard_skip(self) -> None:
        sup = Stage4RiskSupervisor()
        patch_result = sup.evaluate(
            proposal={
                "final_action": "skip",
                "decision_intent": "hard_skip",
                "candidate_side": "NONE",
                "confidence": 0.05,
                "position_size_suggestion": 0,
            },
            account_context={"available_balance": 5000},
            retrieved_patches=[{"action": "block_reentry", "setup_key": "k1"}],
            market_context={"data_quality": "ok", "kline_data_quality": "ok"},
        )
        self.assertEqual(patch_result.veto_reason, "patch_block")

        hard_result = sup.evaluate(
            proposal={
                "final_action": "skip",
                "decision_intent": "hard_skip",
                "candidate_side": "NONE",
                "confidence": 0.05,
                "position_size_suggestion": 0,
            },
            account_context={"available_balance": 5000},
            retrieved_patches=[],
            market_context={"data_quality": "ok", "kline_data_quality": "ok"},
        )
        self.assertEqual(hard_result.veto_reason, "hard_skip")

    def test_decision_log_patch_block_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stage3 = Path(tmp) / "stage3"
            stage3.mkdir()
            append_jsonl(
                stage3 / "applied_learning_patches.jsonl",
                {"symbol": "ETHUSDT", "side": "BUY", "action": "block_reentry", "setup_key": "k1"},
            )
            agent = Stage4AIDecisionAgent(retriever=Stage4PatchRetriever(stage3_dir=stage3))
            decision = agent.decide(
                symbol="ETHUSDT",
                market_context={"last_price": 3250, "prev_price_24h": 3200, "data_quality": "ok", "kline_data_quality": "ok"},
                account_context={"available_balance": 5000},
            )
        self.assertTrue(decision.get("patch_blocked"))
        self.assertEqual(decision.get("matched_patch_count"), 1)
        self.assertEqual(decision["risk_supervisor_result"]["veto_reason"], "patch_block")

    def test_coerce_watch_final_action_to_skip(self) -> None:
        from tools.research.stage4_decision_schema import parse_llm_decision

        raw = {
            "final_action": "watch",
            "symbol": "ETHUSDT",
            "candidate_side": "NONE",
            "confidence": 0.42,
            "why_enter": "",
            "why_skip": "Wait for confirmation",
            "side_reason": "Trend forming",
            "confidence_reason": "watch band",
            "risk_notes": [],
            "patch_awareness": "",
            "uncertainty": "medium",
            "requires_manual_review": False,
        }
        proposal, ok, err = parse_llm_decision(raw, symbol="ETHUSDT")
        self.assertTrue(ok, err)
        self.assertEqual(proposal["final_action"], "skip")
        self.assertEqual(proposal["decision_intent"], "watch")

    def test_parse_watch_and_enter_candidate_intent(self) -> None:
        from tools.research.stage4_decision_schema import parse_llm_decision

        for intent, conf in (("watch", 0.42), ("enter_candidate", 0.62)):
            raw = {
                "final_action": "skip",
                "symbol": "ETHUSDT",
                "candidate_side": "NONE",
                "confidence": conf,
                "decision_intent": intent,
                "why_enter": "",
                "why_skip": "Wait for confirmation",
                "side_reason": "Trend forming",
                "confidence_reason": intent,
                "risk_notes": [],
                "patch_awareness": "",
                "uncertainty": "medium",
                "requires_manual_review": False,
            }
            proposal, ok, _ = parse_llm_decision(raw, symbol="ETHUSDT")
            self.assertTrue(ok)
            self.assertEqual(proposal["decision_intent"], intent)
            self.assertGreaterEqual(proposal["confidence"], 0.30)

    def test_export_bundle_excludes_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "ai_decisions.jsonl").write_text('{"order_sent": false}\n', encoding="utf-8")
            (out / "llm_client_debug.jsonl").write_text('{"error_message_safe": "[REDACTED]"}\n', encoding="utf-8")
            (out / "stage4_ai_decision_summary.json").write_text("{}", encoding="utf-8")
            from tools.research.export_stage4_ai_decision_bundle import export_bundle

            result = export_bundle(out)
            self.assertTrue(result.get("bundle_safe"))
            self.assertTrue(Path(result["bundle_path"]).is_file())

    def test_agent_stage3_availability_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agent = Stage4AIDecisionAgent(retriever=Stage4PatchRetriever(stage3_dir=Path(tmp)))
            decision = agent.decide(
                symbol="ETHUSDT",
                market_context={"last_price": 3250, "prev_price_24h": 3200, "data_quality": "ok"},
                account_context={"available_balance": 5000},
            )
        self.assertIn("stage3_context_available", decision)
        self.assertFalse(decision["stage3_context_available"])
        self.assertEqual(decision["recent_trade_results_count"], 0)


class Stage45RateLimitTests(unittest.TestCase):
    def test_429_raises_provider_rate_limited_no_decision_row(self) -> None:
        from tools.research.stage4_llm_client import ProviderRateLimited

        class RateLimitLLM:
            config = type("C", (), {"provider": "groq"})()

            def complete_json(self, messages, prompt_hash="", symbol="", use_rate_gate=True):
                return {
                    "status": "error",
                    "error_type": "rate_limit",
                    "http_status": 429,
                    "retry_count": 0,
                    "parsed": {},
                    "raw_content_empty": True,
                    "provider": "groq",
                    "model": "test-model",
                }

        agent = Stage4AIDecisionAgent(use_real_llm=False, llm_client=RateLimitLLM())
        agent.real_llm_used = True
        agent.is_mock_ai = False
        agent.model_name = "test-model"
        with self.assertRaises(ProviderRateLimited):
            agent.decide(
                symbol="ETHUSDT",
                market_context={"last_price": 3250, "data_quality": "ok", "kline_data_quality": "ok"},
                account_context={"available_balance": 5000},
            )

    def test_runner_skipped_tick_writes_system_event_not_decision(self) -> None:
        from tools.research.stage4_llm_client import ProviderRateLimited
        from tools.research.run_stage4_ai_decision_dry_run import run_dry_run

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            os.environ["STAGE4_OUTPUT_DIR"] = str(out)
            try:
                def _raise_rate_limit(**kwargs):
                    raise ProviderRateLimited(
                        provider="groq",
                        model_name="test-model",
                        symbol=kwargs.get("symbol", "ETHUSDT"),
                        retry_count=0,
                    )

                with patch(
                    "tools.research.run_stage4_ai_decision_dry_run._fetch_market",
                    return_value={"last_price": 3250, "data_quality": "ok", "kline_data_quality": "ok", "symbol": "ETHUSDT"},
                ), patch(
                    "tools.research.run_stage4_ai_decision_dry_run._fetch_account",
                    return_value={"available_balance": 5000, "open_positions": 0},
                ), patch(
                    "tools.research.stage4_ai_decision_agent.Stage4AIDecisionAgent.decide",
                    side_effect=_raise_rate_limit,
                ), patch(
                    "tools.research.run_stage4_ai_decision_dry_run.require_real_llm_enabled",
                    return_value=False,
                ):
                    summary = run_dry_run(
                        duration_minutes=0.01,
                        poll_interval_seconds=0,
                        symbols=["ETHUSDT"],
                        output_dir=out,
                        use_real_llm=True,
                    )
                self.assertEqual(summary.get("decision_count"), 0)
                self.assertGreaterEqual(summary.get("skipped_tick_count", 0), 1)
                self.assertFalse((out / "ai_decisions.jsonl").is_file())
                self.assertTrue((out / "stage4_system_events.jsonl").is_file())
            finally:
                os.environ.pop("STAGE4_OUTPUT_DIR", None)

    def test_validator_require_real_llm_fails_on_parse_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_decision(
                out,
                {
                    "decision_id": "d1",
                    "created_at_utc": "2026-01-01T00:00:00Z",
                    "decision_source": "ai_decision_agent",
                    "mode": "dry_run",
                    "model_name": "llama-3.3-70b-versatile",
                    "is_mock_ai": False,
                    "real_llm_used": True,
                    "fallback_to_mock": False,
                    "prompt_hash": "abc",
                    "symbol": "ETHUSDT",
                    "candidate_side": "NONE",
                    "final_action": "skip",
                    "confidence": 0.0,
                    "position_size_suggestion": 0,
                    "market_context": {"symbol": "ETHUSDT", "data_quality": "ok"},
                    "account_context": {"available_balance": 5000},
                    "retrieved_patches": [],
                    "why_enter": "",
                    "why_skip": "empty",
                    "side_reason": "test",
                    "confidence_reason": "test",
                    "risk_notes": [],
                    "parse_error": True,
                    "parse_error_type": "rate_limit",
                    "raw_content_empty": True,
                    "safety_constraints": {},
                    "risk_supervisor_result": {"approved": False, "final_decision": "skip"},
                    "final_decision": "skip",
                    "order_sent": False,
                },
            )
            (out / "llm_client_debug.jsonl").write_text('{"success": false}\n', encoding="utf-8")
            (out / "stage4_ai_decision_summary.json").write_text(
                json.dumps({"dry_run_completed": True, "real_successful_llm_decision_count": 0}),
                encoding="utf-8",
            )
            from tools.research.validate_stage4_ai_decision_outputs import validate

            result = validate(out, require_real_llm=True)
            self.assertFalse(result["passed"])
            self.assertTrue(any("parse_error" in e for e in result["errors"]))

    def test_validator_fails_when_no_successful_llm_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "llm_client_debug.jsonl").write_text('{"success": true}\n', encoding="utf-8")
            (out / "stage4_ai_decision_summary.json").write_text(
                json.dumps({"dry_run_completed": True, "skipped_tick_count": 2}),
                encoding="utf-8",
            )
            from tools.research.validate_stage4_ai_decision_outputs import validate

            result = validate(out, require_real_llm=True)
            self.assertFalse(result["passed"])
            self.assertIn("real_successful_llm_decision_count_zero", result["errors"])

    def test_import_stage3_context_seed_creates_jsonl(self) -> None:
        from tools.research.stage4_context_summary import import_stage3_context_seed, load_stage3_context

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            trade = src / "trade_results.jsonl"
            trade.write_text(
                json.dumps({"symbol": "ETHUSDT", "side": "BUY", "close_pnl": -0.1}) + "\n",
                encoding="utf-8",
            )
            target = Path(tmp) / "stage3"
            result = import_stage3_context_seed(trade, target_dir=target, overwrite=True)
            self.assertTrue(result.get("success"))
            ctx = load_stage3_context(target, symbol="ETHUSDT")
            self.assertTrue(ctx["stage3_context_available"])
            self.assertEqual(ctx["recent_trade_results_count"], 1)

    def test_system_event_log_excludes_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["STAGE4_OUTPUT_DIR"] = str(Path(tmp))
            try:
                from tools.research.stage4_system_events import append_system_event

                append_system_event(
                    {
                        "event_type": "provider_rate_limited",
                        "provider": "groq",
                        "model_name": "test",
                        "symbol": "ETHUSDT",
                        "action": "skip_tick_no_decision",
                        "order_sent": False,
                    }
                )
                text = (Path(tmp) / "stage4_system_events.jsonl").read_text(encoding="utf-8")
                self.assertNotIn("gsk_", text)
            finally:
                os.environ.pop("STAGE4_OUTPUT_DIR", None)


class Stage46aContextGuardTests(unittest.TestCase):
    def test_require_stage3_context_blocks_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            env = {
                "STAGE4_OUTPUT_DIR": str(out),
                "STAGE3_OUTPUT_DIR": str(out / "missing_stage3"),
                "STAGE4_REQUIRE_STAGE3_CONTEXT": "true",
            }
            with patch.dict(os.environ, env, clear=False):
                from tools.research.run_stage4_ai_decision_dry_run import preflight_stage3_context

                ok, reason, summary = preflight_stage3_context(
                    output_dir=out,
                    duration_minutes=20,
                    poll_interval_seconds=180,
                    symbols=["ETHUSDT"],
                    mode="dry-run",
                    use_real_llm=True,
                )
            self.assertFalse(ok)
            self.assertEqual(reason, "missing_required_stage3_context")
            self.assertIsNotNone(summary)
            self.assertFalse(summary.get("dry_run_completed"))
            self.assertEqual(summary.get("failed_reason"), "missing_required_stage3_context")
            self.assertEqual(summary.get("order_sent_count"), 0)
            self.assertTrue((out / "stage4_ai_decision_summary.json").is_file())

    def test_require_stage3_context_allows_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stage3 = Path(tmp) / "stage3"
            stage3.mkdir()
            (stage3 / "trade_results.jsonl").write_text(
                json.dumps({"symbol": "ETHUSDT", "side": "BUY", "close_pnl": -0.1}) + "\n",
                encoding="utf-8",
            )
            (stage3 / "reflection_records.jsonl").write_text(
                json.dumps({"symbol": "ETHUSDT", "side": "BUY", "failure_reason": "demo"}) + "\n",
                encoding="utf-8",
            )
            (stage3 / "applied_learning_patches.jsonl").write_text(
                json.dumps({"symbol": "ETHUSDT", "side": "BUY", "action": "block"}) + "\n",
                encoding="utf-8",
            )
            env = {"STAGE3_OUTPUT_DIR": str(stage3), "STAGE4_REQUIRE_STAGE3_CONTEXT": "true"}
            with patch.dict(os.environ, env, clear=False):
                from tools.research.run_stage4_ai_decision_dry_run import preflight_stage3_context

                ok, reason, summary = preflight_stage3_context(
                    output_dir=Path(tmp) / "out",
                    duration_minutes=20,
                    poll_interval_seconds=180,
                    symbols=["ETHUSDT"],
                    mode="dry-run",
                    use_real_llm=True,
                )
            self.assertTrue(ok)
            self.assertEqual(reason, "")
            self.assertIsNone(summary)

    def test_fail_summary_only_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            env = {"STAGE4_OUTPUT_DIR": str(out)}
            script = [
                sys.executable,
                str(ROOT / "tools" / "research" / "run_stage4_ai_decision_dry_run.py"),
                "--fail-summary-only",
                "--failed-reason",
                "missing_required_stage3_context",
                "--output-dir",
                str(out),
                "--symbols",
                "ETHUSDT",
            ]
            with patch.dict(os.environ, env, clear=False):
                proc = subprocess.run(script, capture_output=True, text=True, cwd=str(ROOT))
            self.assertNotEqual(proc.returncode, 0)
            summary = json.loads((out / "stage4_ai_decision_summary.json").read_text(encoding="utf-8"))
            self.assertFalse(summary.get("dry_run_completed"))
            self.assertEqual(summary.get("failed_reason"), "missing_required_stage3_context")

    def test_summary_written_when_all_ticks_skipped(self) -> None:
        from tools.research.stage4_llm_client import ProviderRateLimited

        class SkippingAgent:
            real_llm_used = True
            is_mock_ai = False
            model_name = "test-model"
            fallback_to_mock = False

            def decide(self, **kwargs):
                raise ProviderRateLimited(
                    provider="groq",
                    model_name="test-model",
                    symbol="ETHUSDT",
                    reason="rate_limit",
                )

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            env = {
                "STAGE4_OUTPUT_DIR": str(out),
                "STAGE4_REQUIRE_REAL_LLM": "false",
                "STAGE4_ALLOW_MOCK_FALLBACK": "true",
            }
            with patch.dict(os.environ, env, clear=False):
                agent_mod = __import__(
                    "tools.research.stage4_ai_decision_agent",
                    fromlist=["Stage4AIDecisionAgent"],
                )
                from tools.research.run_stage4_ai_decision_dry_run import run_dry_run

                with patch.object(agent_mod, "Stage4AIDecisionAgent", return_value=SkippingAgent()), patch(
                    "tools.research.run_stage4_ai_decision_dry_run._fetch_market",
                    return_value={"symbol": "ETHUSDT", "last_price": 3000},
                ), patch(
                    "tools.research.run_stage4_ai_decision_dry_run._fetch_account",
                    return_value={"available_balance": 5000, "open_positions": 0},
                ):
                    summary = run_dry_run(
                        duration_minutes=0.01,
                        poll_interval_seconds=0,
                        symbols=["ETHUSDT"],
                        mode="dry-run",
                        output_dir=out,
                        use_real_llm=True,
                    )
            self.assertTrue(summary.get("dry_run_completed"))
            self.assertTrue((out / "stage4_ai_decision_summary.json").is_file())
            self.assertGreaterEqual(summary.get("skipped_tick_count", 0), 1)
            self.assertEqual(summary.get("order_sent_count"), 0)
            self.assertIn("bundle_export", summary)

    def test_check_stage3_context_seed_no_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stage3 = Path(tmp) / "stage3"
            stage3.mkdir()
            (stage3 / "trade_results.jsonl").write_text('{"symbol":"ETHUSDT"}\n', encoding="utf-8")
            (stage3 / "reflection_records.jsonl").write_text('{"symbol":"ETHUSDT"}\n', encoding="utf-8")
            (stage3 / "applied_learning_patches.jsonl").write_text('{"symbol":"ETHUSDT","action":"block"}\n', encoding="utf-8")
            from tools.research.check_stage3_context_seed import check_stage3_context

            result = check_stage3_context(target_dir=stage3)
            blob = json.dumps(result)
            self.assertNotIn("gsk_", blob)
            self.assertNotIn("api_key", blob.lower())


class Stage46cRateLimitDiagnosisTests(unittest.TestCase):
    def test_gate_block_reason_backoff_vs_local(self) -> None:
        from tools.research.stage4_rate_limit_gate import Stage4LLMRateGate
        import time as _time

        Stage4LLMRateGate.reset_shared()
        gate = Stage4LLMRateGate.shared()
        gate.record_rate_limit(backoff_seconds=60)
        self.assertEqual(gate.block_reason(), "backoff_active_skip")
        Stage4LLMRateGate.reset_shared()
        gate2 = Stage4LLMRateGate.shared()
        gate2.record_call_start()
        _time.sleep(0.01)
        with patch.dict(os.environ, {"STAGE4_LLM_MIN_INTERVAL_SECONDS": "9999"}, clear=False):
            gate3 = Stage4LLMRateGate.shared()
            self.assertEqual(gate3.block_reason(), "local_rate_gate_skip")

    def test_skipped_tick_event_type_http_429(self) -> None:
        from tools.research.stage4_llm_client import ProviderRateLimited
        from tools.research.run_stage4_ai_decision_dry_run import _record_skipped_tick, _empty_run_stats

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["STAGE4_OUTPUT_DIR"] = str(Path(tmp))
            try:
                exc = ProviderRateLimited(
                    provider="groq",
                    model_name="llama-3.3-70b-versatile",
                    symbol="ETHUSDT",
                    reason="rate_limit",
                    http_status=429,
                )
                stats = _empty_run_stats()
                _record_skipped_tick(exc=exc, tick=1, stats=stats)
                row = json.loads((Path(tmp) / "stage4_system_events.jsonl").read_text().strip())
                self.assertEqual(row["event_type"], "provider_http_429")
                self.assertEqual(row["http_status"], 429)
            finally:
                os.environ.pop("STAGE4_OUTPUT_DIR", None)

    def test_analyze_46b_style_debug_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            debug_rows = [
                {"created_at_utc": "2026-06-28T16:05:48Z", "http_status": 429, "error_type": "rate_limit", "success": False, "call_kind": "decision"},
                {"created_at_utc": "2026-06-28T16:30:52Z", "http_status": 200, "error_type": None, "success": True, "call_kind": "decision"},
            ]
            (out / "llm_client_debug.jsonl").write_text("\n".join(json.dumps(r) for r in debug_rows) + "\n", encoding="utf-8")
            (out / "stage4_system_events.jsonl").write_text(
                json.dumps({"event_type": "provider_rate_limited", "reason": "rate_limit", "created_at_utc": "2026-06-28T16:05:48Z"})
                + "\n",
                encoding="utf-8",
            )
            (out / "stage4_ai_decision_summary.json").write_text(
                json.dumps({"poll_interval_seconds": 300, "provider_rate_limit_count": 5, "skipped_tick_count": 5}),
                encoding="utf-8",
            )
            from tools.research.analyze_stage4_rate_limit_events import analyze_rate_limit_events

            report = analyze_rate_limit_events(out)
            self.assertGreaterEqual(report["debug_http_429_count"], 1)
            self.assertEqual(report["debug_success_count"], 1)
            self.assertIn("suggested_poll_interval_seconds", report)

    def test_healthcheck_skipped_by_gate_does_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["STAGE4_OUTPUT_DIR"] = str(Path(tmp))
            try:
                with patch("tools.research.check_stage4_llm_provider.Stage4LLMClient") as mock_cls:
                    inst = mock_cls.return_value
                    inst.availability.return_value = {"real_llm_available": True}
                    inst.complete_json.return_value = {
                        "status": "error",
                        "error_type": "backoff_active_skip",
                        "seconds_since_last_llm_call": 10,
                        "required_wait_seconds": 80,
                        "backoff_until_utc": "2026-06-28T17:00:00Z",
                    }
                    from tools.research.check_stage4_llm_provider import run_health_check

                    report = run_health_check(provider="groq", model="llama-3.3-70b-versatile")
                    self.assertTrue(report.get("provider_health_check_passed"))
                    self.assertTrue(report.get("healthcheck_skipped_by_gate"))
            finally:
                os.environ.pop("STAGE4_OUTPUT_DIR", None)


class Stage47ProviderChainTests(unittest.TestCase):
    def _valid_parsed(self) -> Dict[str, Any]:
        return {
            "final_action": "skip",
            "symbol": "ETHUSDT",
            "candidate_side": "NONE",
            "confidence": 0.52,
            "decision_intent": "watch",
            "why_enter": "",
            "why_skip": "Wait",
            "side_reason": "Flat",
            "confidence_reason": "Moderate",
            "risk_notes": [],
            "patch_awareness": "",
            "uncertainty": "medium",
            "requires_manual_review": False,
        }

    def test_dedupe_groq_duplicate_primary_secondary(self) -> None:
        from tools.research.stage4_provider_chain import dedupe_groq_api_keys, deduped_groq_key_envs

        with patch.dict(
            os.environ,
            {
                "GROQ_API_KEY_PRIMARY": "same-test-key-value",
                "GROQ_API_KEY_SECONDARY": "same-test-key-value",
                "GROQ_API_KEY": "same-test-key-value",
            },
            clear=False,
        ):
            status = dedupe_groq_api_keys()
            self.assertTrue(status["provider_chain_deduped"])
            self.assertEqual(status["deduped_provider_key_count"], 1)
            self.assertEqual(len(deduped_groq_key_envs()), 1)
            self.assertEqual(len(status["groq_key_fingerprints"]), 1)

    def test_groq_429_triggers_secondary_real_provider(self) -> None:
        from tools.research.stage4_provider_chain import Stage4ProviderChainClient, Stage4ProviderCircuitBreaker

        Stage4ProviderCircuitBreaker.reset_shared()
        parsed = self._valid_parsed()

        def fake_complete(self, messages, **kwargs):
            prov = self.config.provider
            if prov == "groq":
                return {
                    "status": "error",
                    "error_type": "rate_limit",
                    "http_status": 429,
                    "provider": "groq",
                    "model": "llama-3.3-70b-versatile",
                    "retry_count": 0,
                }
            return {
                "status": "ok",
                "provider": "cerebras",
                "model": "llama-3.3-70b",
                "parsed": parsed,
                "raw_text": json.dumps(parsed),
                "raw_content_empty": False,
            }

        env = {
            "GROQ_API_KEY_PRIMARY": "groq-test-key",
            "CEREBRAS_API_KEY": "cerebras-test-key",
            "STAGE4_LLM_PROVIDER_CHAIN": "groq,cerebras",
            "STAGE4_ALLOW_SECONDARY_REAL_LLM_FALLBACK": "true",
            "STAGE4_ALLOW_MOCK_FALLBACK": "false",
        }
        with patch.dict(os.environ, env, clear=False), patch(
            "tools.research.stage4_llm_client.Stage4LLMClient.complete_json",
            fake_complete,
        ):
            chain = Stage4ProviderChainClient(load_env=False)
            result = chain.complete_json([{"role": "user", "content": "test"}], symbol="ETHUSDT")
        self.assertEqual(result.get("status"), "ok")
        self.assertEqual(result.get("provider"), "cerebras")
        self.assertTrue(result.get("fallback_used"))
        self.assertEqual(result.get("fallback_reason"), "groq_rate_limited")
        attempts = result.get("provider_attempts") or []
        self.assertEqual(attempts[0]["result"], "rate_limited")
        self.assertEqual(attempts[1]["result"], "success")

    def test_cerebras_malformed_does_not_fallback_mock(self) -> None:
        from tools.research.stage4_ai_decision_agent import Stage4AIDecisionAgent

        class BadThenSkipLLM:
            provider_chain = ["groq", "cerebras"]

            def availability(self):
                return {"real_llm_available": True, "provider": "groq", "model_name": "m1"}

            def complete_json(self, messages, **kwargs):
                return {
                    "status": "error",
                    "error_type": "json_parse_failed",
                    "provider": "cerebras",
                    "model": "llama-3.3-70b",
                    "parsed": {},
                    "raw_text": "not-json",
                    "raw_content_empty": False,
                    "provider_chain": ["groq", "cerebras"],
                    "provider_attempts": [
                        {"provider": "groq", "result": "rate_limited", "error_type": "rate_limit"},
                        {"provider": "cerebras", "result": "error", "error_type": "json_parse_failed"},
                    ],
                    "fallback_used": True,
                    "fallback_reason": "groq_rate_limited",
                    "primary_provider": "groq",
                }

        agent = Stage4AIDecisionAgent(use_real_llm=True, llm_client=BadThenSkipLLM())
        decision = agent.decide(
            symbol="ETHUSDT",
            market_context={"last_price": 3250, "data_quality": "ok", "kline_data_quality": "ok"},
            account_context={"available_balance": 5000},
        )
        self.assertFalse(decision.get("is_mock_ai"))
        self.assertTrue(decision.get("parse_error"))
        self.assertFalse(decision.get("fallback_to_mock"))
        self.assertFalse(decision.get("order_sent"))

    def test_missing_cerebras_key_does_not_fallback_mock(self) -> None:
        from tools.research.stage4_provider_chain import Stage4ProviderChainClient

        env = {
            "GROQ_API_KEY_PRIMARY": "groq-only-key",
            "STAGE4_LLM_PROVIDER_CHAIN": "groq,cerebras",
            "STAGE4_ALLOW_SECONDARY_REAL_LLM_FALLBACK": "true",
            "STAGE4_ALLOW_MOCK_FALLBACK": "false",
        }
        blocked = (
            "CEREBRAS_API_KEY",
            "GROQ_API_KEY",
            "GROQ_API_KEY_SECONDARY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GOOGLE_API_KEY",
        )
        base = {k: v for k, v in os.environ.items() if k not in blocked}
        base.update(env)
        with patch.dict(os.environ, base, clear=True):
            chain = Stage4ProviderChainClient(load_env=False)
            self.assertFalse(chain.secondary_available)
            with patch(
                "tools.research.stage4_llm_client.Stage4LLMClient.complete_json",
                return_value={
                    "status": "error",
                    "error_type": "rate_limit",
                    "http_status": 429,
                    "provider": "groq",
                    "model": "m1",
                },
            ):
                result = chain.complete_json([{"role": "user", "content": "x"}], symbol="ETHUSDT")
        self.assertNotEqual(result.get("status"), "ok")
        self.assertFalse(result.get("fallback_used"))

    def test_provider_attempts_recorded_on_decision(self) -> None:
        from tools.research.stage4_ai_decision_agent import Stage4AIDecisionAgent

        parsed = self._valid_parsed()

        class ChainLLM:
            provider_chain = ["groq", "cerebras"]

            def availability(self):
                return {"real_llm_available": True, "provider": "cerebras", "model_name": "llama-3.3-70b"}

            def complete_json(self, messages, **kwargs):
                return {
                    "status": "ok",
                    "provider": "cerebras",
                    "model": "llama-3.3-70b",
                    "parsed": parsed,
                    "raw_text": json.dumps(parsed),
                    "provider_chain": ["groq", "cerebras"],
                    "provider_attempts": [
                        {"provider": "groq", "result": "rate_limited", "error_type": "provider_http_429"},
                        {"provider": "cerebras", "result": "success"},
                    ],
                    "fallback_used": True,
                    "fallback_reason": "groq_rate_limited",
                    "primary_provider": "groq",
                    "primary_error": "rate_limit",
                }

        agent = Stage4AIDecisionAgent(use_real_llm=True, llm_client=ChainLLM())
        decision = agent.decide(
            symbol="ETHUSDT",
            market_context={"last_price": 3250, "data_quality": "ok", "kline_data_quality": "ok"},
            account_context={"available_balance": 5000},
        )
        self.assertTrue(decision.get("fallback_used"))
        self.assertEqual(decision.get("fallback_reason"), "groq_rate_limited")
        self.assertEqual(decision.get("provider"), "cerebras")
        self.assertEqual(len(decision.get("provider_attempts") or []), 2)
        self.assertFalse(decision.get("order_sent"))

    def test_validator_rejects_mock_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_decision(
                out,
                {
                    "decision_id": "d1",
                    "created_at_utc": "2026-01-01T00:00:00Z",
                    "decision_source": "mock_ai_decision_agent",
                    "mode": "dry_run",
                    "model_name": MOCK_MODEL_NAME,
                    "is_mock_ai": True,
                    "real_llm_used": False,
                    "fallback_to_mock": True,
                    "prompt_hash": "abc",
                    "symbol": "ETHUSDT",
                    "candidate_side": "NONE",
                    "final_action": "skip",
                    "confidence": 0.1,
                    "position_size_suggestion": 0,
                    "market_context": {"symbol": "ETHUSDT"},
                    "account_context": {"available_balance": 5000},
                    "retrieved_patches": [],
                    "why_enter": "",
                    "why_skip": "test",
                    "side_reason": "test",
                    "confidence_reason": "test",
                    "risk_notes": [],
                    "safety_constraints": {},
                    "risk_supervisor_result": {"approved": False, "final_decision": "skip"},
                    "final_decision": "skip",
                    "order_sent": False,
                },
            )
            (out / "llm_client_debug.jsonl").write_text("{}\n", encoding="utf-8")
            from tools.research.validate_stage4_ai_decision_outputs import validate

            result = validate(out, require_real_llm=True)
            self.assertFalse(result["passed"])
            self.assertGreater(result["mock_fallback_attempt_count"], 0)

    def test_validator_accepts_groq_cerebras_real_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_decision(
                out,
                {
                    "decision_id": "d1",
                    "created_at_utc": "2026-01-01T00:00:00Z",
                    "decision_source": "ai_decision_agent",
                    "mode": "dry_run",
                    "model_name": "llama-3.3-70b",
                    "provider": "cerebras",
                    "provider_chain": ["groq", "cerebras"],
                    "provider_attempts": [
                        {"provider": "groq", "result": "rate_limited"},
                        {"provider": "cerebras", "result": "success"},
                    ],
                    "fallback_used": True,
                    "fallback_reason": "groq_rate_limited",
                    "primary_provider": "groq",
                    "is_mock_ai": False,
                    "real_llm_used": True,
                    "fallback_to_mock": False,
                    "prompt_hash": "abc",
                    "symbol": "ETHUSDT",
                    "candidate_side": "NONE",
                    "final_action": "skip",
                    "confidence": 0.52,
                    "position_size_suggestion": 0,
                    "market_context": {"symbol": "ETHUSDT", "data_quality": "ok"},
                    "account_context": {"available_balance": 5000},
                    "retrieved_patches": [],
                    "why_enter": "",
                    "why_skip": "watch",
                    "side_reason": "test",
                    "confidence_reason": "test",
                    "risk_notes": [],
                    "decision_intent": "watch",
                    "safety_constraints": {},
                    "risk_supervisor_result": {"approved": False, "final_decision": "skip"},
                    "final_decision": "skip",
                    "order_sent": False,
                },
            )
            (out / "llm_client_debug.jsonl").write_text('{"success": true}\n', encoding="utf-8")
            (out / "stage4_ai_decision_summary.json").write_text(
                json.dumps({"dry_run_completed": True}),
                encoding="utf-8",
            )
            from tools.research.validate_stage4_ai_decision_outputs import validate

            result = validate(out, require_real_llm=True)
            self.assertTrue(result["passed"])
            self.assertEqual(result["provider_success_distribution"].get("cerebras"), 1)

    def test_circuit_breaker_trips_on_groq_429(self) -> None:
        import io
        import urllib.error

        from tools.research.stage4_provider_chain import Stage4ProviderCircuitBreaker
        from tools.research.stage4_llm_client import Stage4LLMClient, Stage4LLMConfig

        Stage4ProviderCircuitBreaker.reset_shared()

        def raise_429(*_args, **_kwargs):
            body = io.BytesIO(b'{"error":"rate limit"}')
            raise urllib.error.HTTPError("https://api.groq.com", 429, "Too Many Requests", {}, body)

        cfg = Stage4LLMConfig(
            provider="groq",
            model="llama-3.3-70b-versatile",
            api_key_env="GROQ_API_KEY_PRIMARY",
            endpoint="https://api.groq.com/openai/v1/chat/completions",
        )
        client = Stage4LLMClient(provider="groq", model=cfg.model, load_env=False)
        client.config = cfg
        client.available = True
        with patch.object(client, "_http_post", side_effect=raise_429):
            with patch.dict(os.environ, {"GROQ_API_KEY_PRIMARY": "test-key"}, clear=False):
                result = client.complete_json([{"role": "user", "content": "hi"}], use_rate_gate=False)
        self.assertEqual(result.get("error_type"), "rate_limit")
        cb = Stage4ProviderCircuitBreaker.shared()
        self.assertTrue(cb.is_open("groq"))
        self.assertGreaterEqual(cb.triggered_count, 1)


class Stage4StrictEnvReadonlyTests(unittest.TestCase):
    def _stage4_readonly_env(self) -> dict[str, str]:
        return {
            "STAGE3_STARTUP_MODE": "idle",
            "OPERATOR_GO_STAGE3_24H_RUNNER": "false",
            "STAGE4_DRY_RUN_ONLY": "true",
            "STAGE4_ORDER_ALLOWED": "false",
            "STAGE4_REQUIRE_REAL_LLM": "true",
            "STAGE4_ALLOW_MOCK_FALLBACK": "false",
            "PRIVATE_ORDER_ENDPOINT_BLOCKED": "true",
            "PAPER_ONLY": "true",
            "BYBIT_SHADOW_MODE": "true",
            "BYBIT_ORDER_ALLOWED": "false",
            "EXCHANGE_WRITE_ALLOWED": "false",
            "RESEARCH_ONLY": "true",
            "BYBIT_DEMO_LEARNING_MODE": "true",
            "BYBIT_ORDER_SCOPE": "demo_or_testnet_only",
            "BYBIT_MAINNET_ALLOWED": "false",
            "BYBIT_M0_BASE_URL": "https://api-demo.bybit.com",
            "EXCHANGE_WRITE_SCOPE": "bybit_demo_or_testnet_only",
            "REAL_MONEY": "false",
            "LIVE_TRADING": "false",
            "PRODUCTION_PROMOTION_ALLOWED": "false",
            "ARM_ALLOWED": "false",
            "MAX_MARGIN_USD": "20",
            "MAX_LEVERAGE": "3",
            "MAX_OPEN_POSITIONS": "1",
            "REQUIRE_STOP_LOSS": "true",
            "REQUIRE_MAX_HOLD": "true",
            "REQUIRE_REFLECTION_ON_LOSS": "true",
            "REQUIRE_PATCH_BEFORE_NEXT_SAME_SETUP": "true",
            "NEXUS_DATA_DIR": "/data",
            "BYBIT_DEMO_API_KEY": "test-demo-key",
            "BYBIT_DEMO_API_SECRET": "test-demo-secret",
        }

    def test_stage4_readonly_allows_write_blocked_env(self) -> None:
        from tools.research.check_bybit_demo_learning_env import run_strict_check

        with patch.dict(os.environ, self._stage4_readonly_env(), clear=True), patch(
            "tools.research.check_bybit_demo_learning_env.evidence_chain_ok",
            return_value=True,
        ), patch(
            "tools.research.check_bybit_demo_learning_env.run_strict_check.__defaults__",
            None,
        ):
            result = run_strict_check(load_local_env=False, check_package=False)
        self.assertTrue(result["strict_env_passed"], result.get("strict_env_errors"))

    def test_stage4_readonly_fails_without_require_real_llm(self) -> None:
        from tools.research.check_bybit_demo_learning_env import run_strict_check

        env = self._stage4_readonly_env()
        env["STAGE4_REQUIRE_REAL_LLM"] = "false"
        with patch.dict(os.environ, env, clear=True), patch(
            "tools.research.check_bybit_demo_learning_env.evidence_chain_ok",
            return_value=True,
        ):
            result = run_strict_check(load_local_env=False, check_package=False)
        self.assertFalse(result["strict_env_passed"])
        # Without REQUIRE_REAL_LLM, read-only exception is inactive → normal strict rules apply
        self.assertIn("env_not_true:BYBIT_ORDER_ALLOWED", result["strict_env_errors"])

    def test_stage4_readonly_fails_when_runner_enabled(self) -> None:
        from tools.research.check_bybit_demo_learning_env import run_strict_check

        env = self._stage4_readonly_env()
        env["OPERATOR_GO_STAGE3_24H_RUNNER"] = "true"
        with patch.dict(os.environ, env, clear=True), patch(
            "tools.research.check_bybit_demo_learning_env.evidence_chain_ok",
            return_value=True,
        ):
            result = run_strict_check(load_local_env=False, check_package=False)
        self.assertFalse(result["strict_env_passed"])


class Stage410ShadowCompareTests(unittest.TestCase):
    def _base_decision(self, **overrides: Any) -> Dict[str, Any]:
        row = {
            "decision_id": "test-decision-1",
            "created_at_utc": "2026-06-29T01:00:00Z",
            "symbol": "ETHUSDT",
            "provider": "groq",
            "decision_intent": "hard_skip",
            "final_action": "skip",
            "confidence": 0.1,
            "regime": "volatile",
            "candidate_side": "NONE",
            "stage3_context_available": True,
            "order_sent": False,
            "is_mock_ai": False,
            "market_context": {"last_price": 1000.0, "regime": "volatile"},
        }
        row.update(overrides)
        return row

    def _flat_klines(self, **kwargs: Any) -> List[Dict[str, Any]]:
        start = kwargs["start_ms"]
        end = kwargs["end_ms"]
        rows: List[Dict[str, Any]] = []
        t = start
        while t <= end:
            rows.append({"start_ms": t, "open": 1000.0, "high": 1000.2, "low": 999.8, "close": 1000.0})
            t += 60_000
        return rows

    def _rising_klines(self, **kwargs: Any) -> List[Dict[str, Any]]:
        start = kwargs["start_ms"]
        end = kwargs["end_ms"]
        rows: List[Dict[str, Any]] = []
        t = start
        i = 0
        while t <= end:
            px = 1000.0 + i * 5.0
            rows.append({"start_ms": t, "open": px, "high": px + 1, "low": px - 0.5, "close": px})
            t += 60_000
            i += 1
        return rows

    def _choppy_klines(self, **kwargs: Any) -> List[Dict[str, Any]]:
        start = kwargs["start_ms"]
        end = kwargs["end_ms"]
        rows: List[Dict[str, Any]] = []
        t = start
        i = 0
        while t <= end:
            px = 1000.0 + (2.0 if i % 2 == 0 else -2.0)
            rows.append({"start_ms": t, "open": px, "high": px + 1.5, "low": px - 1.5, "close": px})
            t += 60_000
            i += 1
        return rows

    def _falling_klines(self, **kwargs: Any) -> List[Dict[str, Any]]:
        start = kwargs["start_ms"]
        end = kwargs["end_ms"]
        rows: List[Dict[str, Any]] = []
        t = start
        i = 0
        while t <= end:
            px = 1000.0 - i * 4.0
            rows.append({"start_ms": t, "open": px, "high": px + 0.5, "low": px - 2.0, "close": px})
            t += 60_000
            i += 1
        return rows

    def test_shadow_compare_reads_decision_jsonl(self) -> None:
        from tools.research.stage4_shadow_compare import run_shadow_compare

        with tempfile.TemporaryDirectory() as tmp:
            dec_dir = Path(tmp) / "decisions"
            out_dir = Path(tmp) / "out"
            dec_dir.mkdir()
            (dec_dir / "ai_decisions.jsonl").write_text(
                json.dumps(self._base_decision()) + "\n",
                encoding="utf-8",
            )
            result = run_shadow_compare(
                decisions_dir=dec_dir,
                output_dir=out_dir,
                symbol="ETHUSDT",
                kline_fetcher=self._flat_klines,
            )
            self.assertEqual(result["summary"]["decision_count"], 1)
            self.assertTrue((out_dir / "shadow_compare.jsonl").is_file())

    def test_missing_future_data_does_not_crash(self) -> None:
        from tools.research.stage4_shadow_compare import compare_decision, parse_utc_iso

        decision = self._base_decision()
        now = parse_utc_iso("2026-06-29T01:15:00Z")
        row = compare_decision(
            decision,
            symbol="ETHUSDT",
            horizons_minutes=[15, 30, 60],
            now_utc=now,
            kline_fetcher=self._flat_klines,
        )
        self.assertEqual(row["shadow_label"], "insufficient_future_data")

    def test_good_skip_label(self) -> None:
        from tools.research.stage4_shadow_compare import compare_decision, parse_utc_iso

        row = compare_decision(
            self._base_decision(decision_intent="soft_skip"),
            symbol="ETHUSDT",
            horizons_minutes=[60],
            now_utc=parse_utc_iso("2026-06-29T03:00:00Z"),
            kline_fetcher=self._choppy_klines,
        )
        self.assertIn(row["shadow_label"], {"good_skip", "neutral"})

    def test_missed_opportunity_label(self) -> None:
        from tools.research.stage4_shadow_compare import compare_decision, parse_utc_iso

        row = compare_decision(
            self._base_decision(decision_intent="hard_skip", candidate_side="BUY"),
            symbol="ETHUSDT",
            horizons_minutes=[60],
            now_utc=parse_utc_iso("2026-06-29T03:00:00Z"),
            kline_fetcher=self._rising_klines,
        )
        self.assertEqual(row["shadow_label"], "missed_opportunity")

    def test_bad_watch_label(self) -> None:
        from tools.research.stage4_shadow_compare import compare_decision, parse_utc_iso

        row = compare_decision(
            self._base_decision(decision_intent="watch", candidate_side="BUY"),
            symbol="ETHUSDT",
            horizons_minutes=[60],
            now_utc=parse_utc_iso("2026-06-29T03:00:00Z"),
            kline_fetcher=self._falling_klines,
        )
        self.assertIn(row["shadow_label"], {"bad_watch", "missed_opportunity"})

    def test_summary_and_report_written(self) -> None:
        from tools.research.stage4_shadow_compare import run_shadow_compare

        with tempfile.TemporaryDirectory() as tmp:
            dec_dir = Path(tmp) / "decisions"
            out_dir = Path(tmp) / "out"
            dec_dir.mkdir()
            (dec_dir / "ai_decisions.jsonl").write_text(
                json.dumps(self._base_decision()) + "\n",
                encoding="utf-8",
            )
            run_shadow_compare(
                decisions_dir=dec_dir,
                output_dir=out_dir,
                kline_fetcher=self._flat_klines,
            )
            self.assertTrue((out_dir / "stage4_shadow_compare_summary.json").is_file())
            self.assertTrue((out_dir / "stage4_shadow_compare_report.md").is_file())

    def test_order_sent_always_false_and_no_secret(self) -> None:
        from tools.research.stage4_shadow_compare import run_shadow_compare

        with tempfile.TemporaryDirectory() as tmp:
            dec_dir = Path(tmp) / "decisions"
            out_dir = Path(tmp) / "out"
            dec_dir.mkdir()
            (dec_dir / "ai_decisions.jsonl").write_text(
                json.dumps(self._base_decision()) + "\n",
                encoding="utf-8",
            )
            result = run_shadow_compare(
                decisions_dir=dec_dir,
                output_dir=out_dir,
                kline_fetcher=self._flat_klines,
            )
            self.assertEqual(result["summary"]["order_sent_count"], 0)
            blob = (out_dir / "stage4_shadow_compare_summary.json").read_text(encoding="utf-8")
            self.assertNotIn("gsk_", blob)


class Stage4ProviderHealthTests(unittest.TestCase):
    def test_provider_health_check_parse_ok(self) -> None:
        from tools.research.check_stage4_llm_provider import run_health_check

        fake_result = {
            "status": "ok",
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "http_status": 200,
            "raw_content_length": 120,
            "parsed": {
                "final_action": "skip",
                "symbol": "ETHUSDT",
                "candidate_side": "NONE",
                "confidence": 0.0,
                "why_enter": "",
                "why_skip": "health_check",
                "side_reason": "",
                "confidence_reason": "health_check",
                "risk_notes": [],
                "patch_awareness": "",
                "uncertainty": "",
                "requires_manual_review": False,
            },
        }
        with patch("tools.research.check_stage4_llm_provider.Stage4LLMClient") as mock_cls:
            mock_cls.return_value.availability.return_value = {"real_llm_available": True}
            mock_cls.return_value.complete_json.return_value = fake_result
            report = run_health_check(provider="groq", model="llama-3.3-70b-versatile")
        self.assertTrue(report["provider_health_check_passed"])
        self.assertTrue(report["json_parse_ok"])


if __name__ == "__main__":
    unittest.main()
