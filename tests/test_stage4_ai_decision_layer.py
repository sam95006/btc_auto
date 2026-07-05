"""Stage 4 AI Decision Layer tests — dry-run only, no orders."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from collections import Counter
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

    def test_real_llm_unavailable_raises_without_mock_fallback(self) -> None:
        """Real LLM unavailable must hard-fail when mock fallback is disallowed."""
        with patch.dict(
            os.environ,
            {
                "STAGE4_REQUIRE_REAL_LLM": "true",
                "STAGE4_ALLOW_MOCK_FALLBACK": "false",
            },
            clear=False,
        ), patch(
            "tools.research.stage4_provider_chain.Stage4ProviderChainClient.availability",
            return_value={"real_llm_available": False, "reason": "provider_unavailable"},
        ):
            from tools.research.stage4_llm_client import RealLLMRequiredError

            with self.assertRaises(RealLLMRequiredError) as ctx:
                Stage4AIDecisionAgent(use_real_llm=True)
            self.assertIn(ctx.exception.reason, ("provider_unavailable", "missing_real_llm_key", "no_allowed_provider_configured"))

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
            "tools.research.stage4_provider_chain.Stage4ProviderChainClient.availability",
            return_value={"real_llm_available": False, "reason": "provider_unavailable"},
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
                "STAGE4_REQUIRE_STAGE3_CONTEXT": "false",
            }
            with patch.dict(os.environ, env, clear=False):
                from tools.research.run_stage4_ai_decision_dry_run import run_dry_run

                with patch(
                    "tools.research.run_stage4_ai_decision_dry_run.Stage4AIDecisionAgent",
                    return_value=SkippingAgent(),
                ), patch(
                    "tools.research.run_stage4_ai_decision_dry_run._fetch_market",
                    return_value={"symbol": "ETHUSDT", "last_price": 3000},
                ), patch(
                    "tools.research.run_stage4_ai_decision_dry_run._fetch_account",
                    return_value={"available_balance": 5000, "open_positions": 0},
                ), patch(
                    "tools.research.export_stage4_ai_decision_bundle.export_bundle",
                    return_value={"bundle_path": str(out / "bundle.tar.gz"), "bundle_safe": True, "file_count": 1},
                ):
                    summary = run_dry_run(
                        duration_minutes=0.01,
                        poll_interval_seconds=0,
                        symbols=["ETHUSDT"],
                        mode="dry-run",
                        output_dir=out,
                        use_real_llm=True,
                    )
            self.assertFalse(summary.get("dry_run_completed"))
            self.assertTrue(summary.get("partial_completion"))
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
        self.assertEqual(attempts[0]["result"], "failed")
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


class Stage412ProviderExhaustionTests(unittest.TestCase):
    def _valid_parsed(self) -> Dict[str, Any]:
        return {
            "final_action": "skip",
            "symbol": "ETHUSDT",
            "candidate_side": "NONE",
            "confidence": 0.05,
            "decision_intent": "hard_skip",
            "why_enter": "",
            "why_skip": "Skip",
            "side_reason": "Flat",
            "confidence_reason": "Low",
            "risk_notes": [],
            "patch_awareness": "",
            "uncertainty": "high",
            "requires_manual_review": False,
        }

    def test_groq_quota_exhausted_triggers_cerebras_fallback(self) -> None:
        from tools.research.stage4_provider_chain import Stage4ProviderChainClient, Stage4ProviderCircuitBreaker

        Stage4ProviderCircuitBreaker.reset_shared()
        parsed = self._valid_parsed()

        def fake_complete(self, messages, **kwargs):
            prov = self.config.provider
            if prov == "groq":
                return {
                    "status": "error",
                    "error_type": "content_empty",
                    "raw_content_empty": True,
                    "raw_text": "",
                    "provider": "groq",
                    "model": "llama-3.3-70b-versatile",
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
        self.assertEqual(result.get("fallback_reason"), "groq_provider_quota_exhausted")
        self.assertFalse(result.get("is_mock_ai"))

    def test_empty_llm_response_classified_as_quota_exhaustion(self) -> None:
        from tools.research.stage4_llm_client import Stage4LLMClient

        result = {
            "status": "error",
            "error_type": "content_empty",
            "raw_content_empty": True,
            "raw_text": "",
        }
        self.assertTrue(Stage4LLMClient.is_quota_exhaustion_result(result))
        self.assertTrue(Stage4LLMClient.is_chain_fallback_eligible(result))

    def test_cerebras_success_after_groq_exhaustion_writes_provider_attempts(self) -> None:
        from tools.research.stage4_ai_decision_agent import Stage4AIDecisionAgent

        parsed = self._valid_parsed()

        class ChainLLM:
            provider_chain = ["groq", "cerebras"]

            def availability(self):
                return {"real_llm_available": True, "provider": "groq", "model_name": "m1"}

            def complete_json(self, messages, **kwargs):
                return {
                    "status": "ok",
                    "provider": "cerebras",
                    "model": "llama-3.3-70b",
                    "parsed": parsed,
                    "raw_text": json.dumps(parsed),
                    "provider_chain": ["groq", "cerebras"],
                    "provider_attempts": [
                        {"provider": "groq", "result": "failed", "error_type": "provider_quota_exhausted"},
                        {"provider": "cerebras", "result": "success"},
                    ],
                    "fallback_used": True,
                    "fallback_reason": "groq_provider_quota_exhausted",
                    "primary_provider": "groq",
                    "primary_error": "provider_quota_exhausted",
                    "is_mock_ai": False,
                }

        agent = Stage4AIDecisionAgent(use_real_llm=True, llm_client=ChainLLM())
        decision = agent.decide(
            symbol="ETHUSDT",
            market_context={"last_price": 3250, "data_quality": "ok", "kline_data_quality": "ok"},
            account_context={"available_balance": 5000},
        )
        self.assertEqual(decision.get("provider"), "cerebras")
        self.assertTrue(decision.get("fallback_used"))
        self.assertEqual(decision.get("fallback_reason"), "groq_provider_quota_exhausted")
        self.assertEqual(len(decision.get("provider_attempts") or []), 2)
        self.assertFalse(decision.get("order_sent"))

    def test_cerebras_failure_does_not_fallback_mock(self) -> None:
        from tools.research.stage4_provider_chain import Stage4ProviderChainClient

        env = {
            "GROQ_API_KEY_PRIMARY": "groq-test-key",
            "CEREBRAS_API_KEY": "cerebras-test-key",
            "STAGE4_LLM_PROVIDER_CHAIN": "groq,cerebras",
            "STAGE4_ALLOW_SECONDARY_REAL_LLM_FALLBACK": "true",
            "STAGE4_ALLOW_MOCK_FALLBACK": "false",
            "STAGE4_REQUIRE_REAL_LLM": "true",
        }

        def fake_complete(self, messages, **kwargs):
            prov = self.config.provider
            if prov == "groq":
                return {"status": "error", "error_type": "content_empty", "raw_content_empty": True, "raw_text": ""}
            return {"status": "error", "error_type": "content_empty", "raw_content_empty": True, "raw_text": ""}

        with patch.dict(os.environ, env, clear=False), patch(
            "tools.research.stage4_llm_client.Stage4LLMClient.complete_json",
            fake_complete,
        ):
            chain = Stage4ProviderChainClient(load_env=False)
            result = chain.complete_json([{"role": "user", "content": "x"}], symbol="ETHUSDT")
        self.assertEqual(result.get("error_type"), "provider_chain_failed")
        self.assertFalse(result.get("fallback_used"))

    def test_provider_chain_failed_writes_skipped_tick(self) -> None:
        from tools.research.stage4_llm_client import ProviderRateLimited
        from tools.research.run_stage4_ai_decision_dry_run import _empty_run_stats, _record_skipped_tick

        stats = _empty_run_stats()
        exc = ProviderRateLimited(
            provider="cerebras",
            model_name="m1",
            symbol="ETHUSDT",
            reason="provider_chain_failed",
            event_type="provider_chain_failed",
        )
        _record_skipped_tick(exc=exc, tick=1, stats=stats)
        self.assertEqual(stats["provider_chain_failed_count"], 1)
        self.assertEqual(stats["skipped_tick_count"], 1)

    def test_summary_always_written_on_partial_completion(self) -> None:
        from tools.research.run_stage4_ai_decision_dry_run import run_dry_run

        class OneSkipAgent:
            real_llm_used = True
            is_mock_ai = False
            model_name = "test-model"
            fallback_to_mock = False
            _calls = 0

            def decide(self, **kwargs):
                from tools.research.stage4_llm_client import ProviderRateLimited

                self._calls += 1
                if self._calls == 1:
                    raise ProviderRateLimited(
                        provider="groq",
                        model_name="test-model",
                        symbol="ETHUSDT",
                        reason="provider_chain_failed",
                        event_type="provider_chain_failed",
                    )
                return {
                    "decision_id": "d1",
                    "created_at_utc": "2026-01-01T00:00:00Z",
                    "decision_source": "ai_decision_agent",
                    "mode": "dry_run",
                    "model_name": "test-model",
                    "provider": "groq",
                    "is_mock_ai": False,
                    "real_llm_used": True,
                    "fallback_to_mock": False,
                    "prompt_hash": "abc",
                    "symbol": "ETHUSDT",
                    "candidate_side": "NONE",
                    "final_action": "skip",
                    "confidence": 0.05,
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
                }

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            env = {
                "STAGE4_OUTPUT_DIR": str(out),
                "STAGE4_TARGET_EFFECTIVE_DECISION_COUNT": "30",
                "STAGE4_REQUIRE_REAL_LLM": "false",
                "STAGE4_ALLOW_MOCK_FALLBACK": "true",
            }
            agent_mod = __import__(
                "tools.research.stage4_ai_decision_agent",
                fromlist=["Stage4AIDecisionAgent", "write_decision"],
            )
            with patch.dict(os.environ, env, clear=False), patch.object(
                agent_mod, "Stage4AIDecisionAgent", return_value=OneSkipAgent()
            ), patch(
                "tools.research.run_stage4_ai_decision_dry_run._fetch_market",
                return_value={"symbol": "ETHUSDT", "last_price": 3000},
            ), patch(
                "tools.research.run_stage4_ai_decision_dry_run._fetch_account",
                return_value={"available_balance": 5000, "open_positions": 0},
            ), patch.object(agent_mod, "write_decision", side_effect=lambda o, d: None):
                summary = run_dry_run(
                    duration_minutes=0.01,
                    poll_interval_seconds=0,
                    symbols=["ETHUSDT"],
                    mode="dry-run",
                    output_dir=out,
                    use_real_llm=True,
                )
            self.assertTrue((out / "stage4_ai_decision_summary.json").is_file())
            self.assertTrue(summary.get("partial_completion"))
            self.assertFalse(summary.get("dry_run_completed"))

    def test_bundle_exported_on_partial_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "ai_decisions.jsonl").write_text(
                json.dumps(
                    {
                        "decision_id": "d1",
                        "created_at_utc": "2026-01-01T00:00:00Z",
                        "decision_source": "ai_decision_agent",
                        "mode": "dry_run",
                        "model_name": "llama-3.3-70b",
                        "provider": "groq",
                        "is_mock_ai": False,
                        "real_llm_used": True,
                        "fallback_to_mock": False,
                        "prompt_hash": "abc",
                        "symbol": "ETHUSDT",
                        "candidate_side": "NONE",
                        "final_action": "skip",
                        "confidence": 0.05,
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
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (out / "llm_client_debug.jsonl").write_text("{}\n", encoding="utf-8")
            (out / "stage4_ai_decision_summary.json").write_text(
                json.dumps(
                    {
                        "dry_run_completed": False,
                        "partial_completion": True,
                        "effective_decision_count": 1,
                        "target_effective_decision_count": 30,
                    }
                ),
                encoding="utf-8",
            )
            from tools.research.export_stage4_ai_decision_bundle import export_bundle

            bundle = export_bundle(out)
            self.assertTrue(bundle.get("bundle_safe"))
            self.assertGreater(bundle.get("file_count", 0), 0)

    def test_validator_distinguishes_technical_valid_vs_dataset_target_met(self) -> None:
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
                    "provider": "groq",
                    "is_mock_ai": False,
                    "real_llm_used": True,
                    "fallback_to_mock": False,
                    "prompt_hash": "abc",
                    "symbol": "ETHUSDT",
                    "candidate_side": "NONE",
                    "final_action": "skip",
                    "confidence": 0.05,
                    "position_size_suggestion": 0,
                    "market_context": {"symbol": "ETHUSDT", "data_quality": "ok"},
                    "account_context": {"available_balance": 5000},
                    "retrieved_patches": [],
                    "why_enter": "",
                    "why_skip": "test",
                    "side_reason": "test",
                    "confidence_reason": "test",
                    "risk_notes": [],
                    "decision_intent": "hard_skip",
                    "safety_constraints": {},
                    "risk_supervisor_result": {"approved": False, "final_decision": "skip"},
                    "final_decision": "skip",
                    "order_sent": False,
                },
            )
            (out / "llm_client_debug.jsonl").write_text('{"ok": true}\n', encoding="utf-8")
            (out / "stage4_ai_decision_summary.json").write_text(
                json.dumps(
                    {
                        "dry_run_completed": False,
                        "partial_completion": True,
                        "effective_decision_count": 1,
                        "target_effective_decision_count": 30,
                        "failed_reason": "provider_yield_below_target",
                    }
                ),
                encoding="utf-8",
            )
            from tools.research.validate_stage4_ai_decision_outputs import validate

            result = validate(out, require_real_llm=True)
            self.assertTrue(result["technical_valid"])
            self.assertFalse(result["dataset_target_met"])
            self.assertTrue(result["validator_passed"])
            self.assertEqual(result["order_sent_count"], 0)

    def test_groq_multi_key_429_then_401_prefers_rate_limit_for_fallback(self) -> None:
        import io
        import urllib.error

        from tools.research.stage4_llm_client import Stage4LLMClient, Stage4LLMConfig

        calls = {"n": 0}

        def side_effect(*_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] <= 2:
                body = io.BytesIO(b'{"error":"rate limit"}')
                raise urllib.error.HTTPError("https://api.groq.com", 429, "Too Many Requests", {}, body)
            body = io.BytesIO(b'{"error":"invalid"}')
            raise urllib.error.HTTPError("https://api.groq.com", 401, "Unauthorized", {}, body)

        cfg = Stage4LLMConfig(
            provider="groq",
            model="llama-3.3-70b-versatile",
            api_key_env="GROQ_API_KEY_PRIMARY",
            endpoint="https://api.groq.com/openai/v1/chat/completions",
        )
        client = Stage4LLMClient(provider="groq", model=cfg.model, load_env=False)
        client.config = cfg
        client.available = True
        with patch.object(client, "_api_key_chain", return_value=["K1", "K2", "K3"]), patch.object(
            client, "_http_post", side_effect=side_effect
        ):
            result = client.complete_json([{"role": "user", "content": "hi"}], use_rate_gate=False)
        self.assertEqual(result.get("error_type"), "rate_limit")
        self.assertTrue(Stage4LLMClient.is_chain_fallback_eligible(result))

    def test_no_secrets_in_summary_or_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "ai_decisions.jsonl").write_text('{"decision_id":"d1","order_sent":false}\n', encoding="utf-8")
            (out / "llm_client_debug.jsonl").write_text('{"masked": true}\n', encoding="utf-8")
            (out / "stage4_ai_decision_summary.json").write_text(
                json.dumps({"dry_run_completed": False, "partial_completion": True}),
                encoding="utf-8",
            )
            from tools.research.export_stage4_ai_decision_bundle import export_bundle
            from tools.research.validate_stage4_ai_decision_outputs import validate

            bundle = export_bundle(out)
            self.assertNotIn("gsk_", json.dumps(bundle))
            result = validate(out, require_real_llm=False)
            self.assertFalse(result["debug_log_has_api_key"])


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
            requested_symbol="ETHUSDT",
            market_symbol="ETHUSDT",
            horizons_minutes=[15, 30, 60],
            now_utc=now,
            kline_fetcher=self._flat_klines,
        )
        self.assertEqual(row["shadow_label"], "insufficient_future_data")

    def test_good_skip_label(self) -> None:
        from tools.research.stage4_shadow_compare import compare_decision, parse_utc_iso

        row = compare_decision(
            self._base_decision(decision_intent="soft_skip"),
            requested_symbol="ETHUSDT",
            market_symbol="ETHUSDT",
            horizons_minutes=[60],
            now_utc=parse_utc_iso("2026-06-29T03:00:00Z"),
            kline_fetcher=self._choppy_klines,
        )
        self.assertIn(row["shadow_label"], {"good_skip", "neutral"})

    def test_missed_opportunity_label(self) -> None:
        from tools.research.stage4_shadow_compare import compare_decision, parse_utc_iso

        row = compare_decision(
            self._base_decision(decision_intent="hard_skip", candidate_side="BUY"),
            requested_symbol="ETHUSDT",
            market_symbol="ETHUSDT",
            horizons_minutes=[60],
            now_utc=parse_utc_iso("2026-06-29T03:00:00Z"),
            kline_fetcher=self._rising_klines,
        )
        self.assertEqual(row["shadow_label"], "missed_opportunity")

    def test_bad_watch_label(self) -> None:
        from tools.research.stage4_shadow_compare import compare_decision, parse_utc_iso

        row = compare_decision(
            self._base_decision(decision_intent="watch", candidate_side="BUY"),
            requested_symbol="ETHUSDT",
            market_symbol="ETHUSDT",
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


class Stage412a5GroqPayloadTests(unittest.TestCase):
    def test_llama_uses_json_object_not_json_schema(self) -> None:
        from tools.research.stage4_groq_payload import (
            build_stage4_groq_openai_payload,
            groq_payload_metadata,
        )

        meta = groq_payload_metadata()
        self.assertEqual(meta["groq_payload_mode"], "json_object")
        self.assertFalse(meta["json_schema_used"])
        self.assertFalse(meta["strict_schema_used"])
        payload = build_stage4_groq_openai_payload(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Return JSON {\"ok\": true}"}],
            max_tokens=64,
        )
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertNotIn("max_completion_tokens", payload)
        self.assertNotIn("json_schema", json.dumps(payload))

    def test_parse_groq_error_safe_redacts_secrets(self) -> None:
        from tools.research.stage4_groq_payload import parse_groq_error_safe

        body = json.dumps(
            {
                "error": {
                    "type": "invalid_request_error",
                    "message": "bad field gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890",
                },
                "request_id": "req_test123",
            }
        )
        parsed = parse_groq_error_safe(body)
        self.assertEqual(parsed["error_type"], "invalid_request_error")
        self.assertIn("[redacted]", parsed["error_message_safe"] or "")
        self.assertNotIn("gsk_", parsed["error_message_safe"] or "")
        self.assertEqual(parsed["request_id"], "req_test123")

    def test_payload_matrix_records_variants(self) -> None:
        from tools.research.check_groq_auth_minimal import run_payload_matrix

        def fake_probe(*, api_key, variant, model):
            ok = variant in {"bare_chat_no_response_format", "json_object_mode"}
            return {
                "payload_variant": variant,
                "http_status": 200 if ok else 400,
                "auth_success": ok,
                "valid_json": ok,
                "error_type": None if ok else "invalid_request_error",
                "error_message_safe": None if ok else "schema unsupported",
                "request_id": "req_x",
                "model": model,
            }

        def fake_stage4(*, api_key, model):
            return {
                "payload_variant": "stage4_json_object_no_max_completion_tokens",
                "http_status": 200,
                "auth_success": True,
                "valid_json": True,
                "error_type": None,
                "error_message_safe": None,
                "request_id": "req_y",
                "model": model,
            }

        with patch.dict(
            os.environ,
            {"GROQ_API_KEY_PRIMARY": "gsk_testkeyvalue123456789012345678901234567890", "GROQ_API_KEY_SECONDARY": ""},
            clear=False,
        ), patch("tools.research.check_groq_auth_minimal._probe_variant", side_effect=fake_probe), patch(
            "tools.research.check_groq_auth_minimal._probe_stage4_style",
            side_effect=fake_stage4,
        ):
            report = run_payload_matrix()
        variants = {r["payload_variant"] for r in report["payload_matrix_results"]}
        self.assertIn("bare_chat_no_response_format", variants)
        self.assertIn("json_object_mode", variants)
        self.assertIn("json_schema_strict_false", variants)
        self.assertTrue(report["any_groq_auth_success"])
        self.assertGreaterEqual(report["json_object_success_count"], 1)

    def test_capacity_check_includes_groq_payload_mode(self) -> None:
        from tools.research.check_stage4_provider_capacity import run_capacity_check

        with patch(
            "tools.research.check_stage4_provider_capacity.probe_groq_keys_for_capacity",
            return_value={
                "groq_valid_key_count": 1,
                "groq_invalid_key_count": 0,
                "groq_rate_limited_key_count": 0,
                "groq_key_count": 1,
                "groq_error_distribution": {},
                "groq_keys": [],
            },
        ):
            report = run_capacity_check(provider="groq")
        self.assertEqual(report["groq_payload_mode"], "json_object")
        self.assertFalse(report["json_schema_used"])
        self.assertTrue(report["can_start_long_soak"])

    def test_groq_400_records_safe_error_in_client(self) -> None:
        from tools.research.stage4_llm_client import Stage4LLMClient, Stage4LLMConfig

        cfg = Stage4LLMConfig(
            provider="groq",
            model="llama-3.3-70b-versatile",
            api_key_env="GROQ_API_KEY_PRIMARY",
            endpoint="https://api.groq.com/openai/v1/chat/completions",
        )
        client = Stage4LLMClient(load_env=False)
        client.config = cfg
        client.available = True
        err_body = json.dumps(
            {"error": {"type": "invalid_request_error", "message": "max_completion_tokens unsupported"}}
        ).encode("utf-8")

        class FakeHTTPError(urllib.error.HTTPError):
            def __init__(self) -> None:
                super().__init__(
                    url="https://api.groq.com",
                    code=400,
                    msg="Bad Request",
                    hdrs=None,
                    fp=None,
                )

            def read(self) -> bytes:
                return err_body

        with patch.object(client, "_http_post", side_effect=FakeHTTPError()):
            result = client._openai_compat(cfg, [{"role": "user", "content": "json test"}], key_env="GROQ_API_KEY_PRIMARY")
        self.assertEqual(result.get("error_type"), "invalid_request_error")
        self.assertIn("max_completion", result.get("error_message_safe") or "")


class Stage412a4GroqMinimalAuthTests(unittest.TestCase):
    def test_key_format_inspection_detects_whitespace_and_quotes(self) -> None:
        from tools.research.stage4_groq_payload import parse_groq_error_safe

        body = json.dumps({"error": {"type": "invalid_request_error", "message": "x"}})
        parsed = parse_groq_error_safe(body)
        self.assertEqual(parsed["error_type"], "invalid_request_error")

    def test_minimal_auth_report_has_no_secrets(self) -> None:
        from tools.research.check_groq_auth_minimal import run_payload_matrix

        with patch.dict(
            os.environ,
            {"GROQ_API_KEY_PRIMARY": "gsk_testkeyvalue123456789012345678901234567890"},
            clear=False,
        ), patch("tools.research.check_groq_auth_minimal._probe_variant") as probe, patch(
            "tools.research.check_groq_auth_minimal._probe_stage4_style",
            return_value={"payload_variant": "stage4_json_object_no_max_completion_tokens", "auth_success": False},
        ):
            probe.return_value = {
                "payload_variant": "json_object_mode",
                "auth_success": False,
                "http_status": 400,
                "error_type": "invalid_request_error",
            }
            report = run_payload_matrix()
        blob = json.dumps(report)
        self.assertNotIn("gsk_testkeyvalue", blob)
        self.assertFalse(report.get("debug_log_has_api_key"))
        self.assertFalse(report.get("order_sent"))


class Stage412aProviderCapacityTests(unittest.TestCase):
    def setUp(self) -> None:
        from tools.research.stage4_groq_key_registry import GroqKeyRegistry
        from tools.research.stage4_provider_chain import Stage4ProviderCircuitBreaker

        GroqKeyRegistry.reset_shared()
        Stage4ProviderCircuitBreaker.reset_shared()

    def test_invalid_groq_key_disabled(self) -> None:
        from tools.research.stage4_groq_key_registry import GroqKeyRegistry
        from tools.research.stage4_llm_client import GROQ_KEY_ENVS

        registry = GroqKeyRegistry.shared()
        registry.record_error(
            env_name="GROQ_API_KEY_PRIMARY",
            key_value="bad-key-value",
            error_type="http_unauthorized",
            http_status=401,
        )
        self.assertTrue(registry.is_disabled("bad-key-value"))
        env_patch = {name: "" for name in GROQ_KEY_ENVS}
        env_patch["GROQ_API_KEY_PRIMARY"] = "bad-key-value"
        with patch.dict(os.environ, env_patch, clear=False):
            from tools.research.stage4_provider_chain import deduped_groq_key_envs

            self.assertEqual(deduped_groq_key_envs(skip_disabled=True), [])

    def test_groq_401_does_not_block_cerebras_fallback(self) -> None:
        from tools.research.stage4_provider_chain import Stage4ProviderChainClient

        parsed = {
            "final_action": "skip",
            "symbol": "ETHUSDT",
            "candidate_side": "NONE",
            "confidence": 0.05,
            "why_enter": "",
            "why_skip": "ok",
            "side_reason": "x",
            "confidence_reason": "x",
            "risk_notes": [],
            "patch_awareness": "",
            "uncertainty": "high",
            "requires_manual_review": False,
        }

        def fake_complete(self, messages, **kwargs):
            prov = self.config.provider
            if prov == "groq":
                return {"status": "error", "error_type": "http_unauthorized", "http_status": 401}
            return {
                "status": "ok",
                "provider": "cerebras",
                "model": "gpt-oss-120b",
                "parsed": parsed,
                "raw_text": json.dumps(parsed),
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
            result = Stage4ProviderChainClient(load_env=False).complete_json(
                [{"role": "user", "content": "x"}],
                symbol="ETHUSDT",
            )
        self.assertEqual(result.get("status"), "ok")
        self.assertEqual(result.get("provider"), "cerebras")

    def test_groq_429_triggers_cerebras_fallback(self) -> None:
        from tools.research.stage4_provider_chain import Stage4ProviderChainClient

        parsed = {
            "final_action": "skip",
            "symbol": "ETHUSDT",
            "candidate_side": "NONE",
            "confidence": 0.05,
            "why_enter": "",
            "why_skip": "ok",
            "side_reason": "x",
            "confidence_reason": "x",
            "risk_notes": [],
            "patch_awareness": "",
            "uncertainty": "high",
            "requires_manual_review": False,
        }

        def fake_complete(self, messages, **kwargs):
            if self.config.provider == "groq":
                return {"status": "error", "error_type": "rate_limit", "http_status": 429}
            return {
                "status": "ok",
                "provider": "cerebras",
                "model": "gpt-oss-120b",
                "parsed": parsed,
                "raw_text": json.dumps(parsed),
            }

        env = {
            "GROQ_API_KEY_PRIMARY": "groq-test-key",
            "CEREBRAS_API_KEY": "cerebras-test-key",
            "STAGE4_LLM_PROVIDER_CHAIN": "groq,cerebras",
            "STAGE4_ALLOW_SECONDARY_REAL_LLM_FALLBACK": "true",
        }
        with patch.dict(os.environ, env, clear=False), patch(
            "tools.research.stage4_llm_client.Stage4LLMClient.complete_json",
            fake_complete,
        ):
            result = Stage4ProviderChainClient(load_env=False).complete_json(
                [{"role": "user", "content": "x"}],
                symbol="ETHUSDT",
            )
        self.assertEqual(result.get("provider"), "cerebras")
        self.assertTrue(result.get("fallback_used"))

    def test_provider_chain_failed_metrics_include_fallback_attempt(self) -> None:
        from tools.research.stage4_llm_client import ProviderRateLimited
        from tools.research.run_stage4_ai_decision_dry_run import _empty_run_stats, _record_skipped_tick

        stats = _empty_run_stats()
        attempts = [
            {"provider": "groq", "result": "failed", "error_type": "provider_quota_exhausted"},
            {"provider": "cerebras", "result": "failed", "error_type": "rate_limit", "http_status": 429},
        ]
        exc = ProviderRateLimited(
            provider="cerebras",
            model_name="gpt-oss-120b",
            symbol="ETHUSDT",
            reason="provider_chain_failed",
            event_type="provider_chain_failed",
            provider_attempts=attempts,
        )
        _record_skipped_tick(exc=exc, tick=2, stats=stats)
        self.assertEqual(stats["provider_chain_failed_count"], 1)
        self.assertGreaterEqual(stats["fallback_attempt_count"], 1)

    def test_aggregate_provider_attempt_metrics(self) -> None:
        from tools.research.stage4_provider_metrics import aggregate_attempt_metrics_from_attempts

        metrics = aggregate_attempt_metrics_from_attempts(
            [
                [
                    {"provider": "groq", "result": "failed", "error_type": "http_unauthorized", "http_status": 401},
                    {"provider": "cerebras", "result": "failed", "error_type": "rate_limit", "http_status": 429},
                ]
            ],
            chain_failed_count=1,
        )
        self.assertEqual(metrics["groq_401_count"], 1)
        self.assertEqual(metrics["cerebras_429_count"], 1)
        self.assertEqual(metrics["fallback_attempt_count"], 1)
        self.assertEqual(metrics["provider_chain_failed_count"], 1)

    def test_cerebras_404_counted_correctly(self) -> None:
        from tools.research.stage4_provider_metrics import aggregate_attempt_metrics_from_attempts

        metrics = aggregate_attempt_metrics_from_attempts(
            [[{"provider": "cerebras", "result": "failed", "error_type": "http_not_found", "http_status": 404}]],
        )
        self.assertEqual(metrics["cerebras_404_count"], 1)

    def test_capacity_check_can_start_false_when_both_unavailable(self) -> None:
        from tools.research.check_stage4_provider_capacity import run_capacity_check

        with patch("tools.research.check_stage4_provider_capacity.probe_groq_keys_for_capacity") as groq_probe, patch(
            "tools.research.check_stage4_provider_capacity._probe_cerebras_direct"
        ) as cerebras_probe:
            groq_probe.return_value = {
                "groq_valid_key_count": 0,
                "groq_invalid_key_count": 1,
                "groq_rate_limited_key_count": 0,
                "groq_key_count": 1,
                "groq_error_distribution": {"http_unauthorized": 1},
                "groq_keys": [],
            }
            cerebras_probe.return_value = {
                "cerebras_available": True,
                "cerebras_valid_json": False,
                "cerebras_direct_success": False,
                "cerebras_error_type": "rate_limit",
                "cerebras_error_distribution": {"rate_limit": 1},
            }
            report = run_capacity_check()
        self.assertFalse(report["can_start_long_soak"])
        self.assertFalse(report["provider_capacity_ok"])

    def test_capacity_check_can_start_true_when_one_provider_valid(self) -> None:
        from tools.research.check_stage4_provider_capacity import run_capacity_check

        with patch("tools.research.check_stage4_provider_capacity.probe_groq_keys_for_capacity") as groq_probe, patch(
            "tools.research.check_stage4_provider_capacity._probe_cerebras_direct"
        ) as cerebras_probe:
            groq_probe.return_value = {
                "groq_valid_key_count": 1,
                "groq_invalid_key_count": 0,
                "groq_rate_limited_key_count": 0,
                "groq_key_count": 1,
                "groq_error_distribution": {},
                "groq_keys": [],
            }
            cerebras_probe.return_value = {
                "cerebras_available": True,
                "cerebras_valid_json": False,
                "cerebras_direct_success": False,
                "cerebras_error_type": "rate_limit",
                "cerebras_error_distribution": {"rate_limit": 1},
            }
            report = run_capacity_check()
        self.assertTrue(report["can_start_long_soak"])

    def test_capacity_report_has_no_secrets(self) -> None:
        from tools.research.check_stage4_provider_capacity import run_capacity_check

        with patch("tools.research.check_stage4_provider_capacity.probe_groq_keys_for_capacity") as groq_probe, patch(
            "tools.research.check_stage4_provider_capacity._probe_cerebras_direct"
        ) as cerebras_probe:
            groq_probe.return_value = {
                "groq_valid_key_count": 0,
                "groq_invalid_key_count": 0,
                "groq_rate_limited_key_count": 0,
                "groq_key_count": 0,
                "groq_error_distribution": {},
                "groq_keys": [{"fingerprint": "abc12345", "status": "unknown"}],
            }
            cerebras_probe.return_value = {
                "cerebras_available": False,
                "cerebras_valid_json": False,
                "cerebras_direct_success": False,
                "cerebras_error_type": "missing_api_key",
                "cerebras_error_distribution": {},
            }
            report = run_capacity_check()
        blob = json.dumps(report)
        self.assertNotIn("gsk_", blob)
        self.assertFalse(report.get("debug_log_has_api_key"))
        self.assertFalse(report.get("order_sent"))
        self.assertFalse(report.get("mock_used"))


class Stage4CerebrasPayloadTests(unittest.TestCase):
    def test_cerebras_stage4_payload_omits_max_completion_tokens(self) -> None:
        from tools.research.stage4_cerebras_payload import build_stage4_cerebras_openai_payload

        payload = build_stage4_cerebras_openai_payload(
            model="gpt-oss-120b",
            messages=[{"role": "user", "content": "JSON test"}],
            max_tokens=128,
            payload_mode="json_object",
        )
        self.assertIn("max_tokens", payload)
        self.assertNotIn("max_completion_tokens", payload)
        self.assertEqual(payload["response_format"]["type"], "json_object")
        schema_payload = build_stage4_cerebras_openai_payload(
            model="gpt-oss-120b",
            messages=[{"role": "user", "content": "JSON test"}],
            max_tokens=900,
            payload_mode="json_schema",
        )
        self.assertEqual(schema_payload["response_format"]["type"], "json_schema")

    def test_cerebras_matrix_infer_json_schema_unsupported(self) -> None:
        from tools.research.check_cerebras_auth_minimal import _infer_root_cause

        matrix = [
            {"variant": "bare_chat_no_response_format", "auth_success": True, "http_status": 200},
            {"variant": "json_object_mode", "auth_success": True, "http_status": 200},
            {"variant": "json_schema_strict_false", "auth_success": False, "http_status": 400},
        ]
        self.assertEqual(_infer_root_cause(matrix, {}), "json_schema_unsupported_use_json_object_mode")

    def test_cerebras_matrix_tool_no_key(self) -> None:
        from tools.research.check_cerebras_auth_minimal import run_payload_matrix

        with patch.dict(os.environ, {}, clear=True):
            report = run_payload_matrix()
        self.assertFalse(report["cerebras_direct_success"])
        self.assertEqual(report["cerebras_error_root_cause"], "missing_api_key")


class Stage4ProviderYieldAnalysisTests(unittest.TestCase):
    def test_provider_yield_analysis_reads_summary_fields(self) -> None:
        from tools.research.analyze_stage4_provider_yield import analyze_provider_yield

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "stage4_ai_decision_summary.json").write_text(
                json.dumps(
                    {
                        "groq_429_count": 2,
                        "cerebras_attempt_count": 2,
                        "cerebras_success_count": 0,
                        "provider_chain_failed_count": 2,
                        "effective_decision_count": 3,
                        "tick_count": 5,
                        "mock_ai_used_count": 0,
                        "order_sent_count": 0,
                        "parse_error_count": 0,
                    }
                ),
                encoding="utf-8",
            )
            (out / "stage4_30m_dry_run.log").write_text(
                "2026-01-01T00:00:00Z TICK=1 symbol=ETHUSDT final=skip parse_error=False order_sent=False\n"
                "2026-01-01T00:05:00Z TICK=2 SKIPPED symbol=ETHUSDT reason=provider_chain_failed order_sent=false\n",
                encoding="utf-8",
            )
            report = analyze_provider_yield(out)
        self.assertEqual(report["groq_429_count"], 2)
        self.assertEqual(report["cerebras_attempt_count"], 2)
        self.assertEqual(report["effective_decision_count"], 3)


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


class Stage413FixedFleetTests(unittest.TestCase):
    def test_parse_fleet_symbols(self) -> None:
        from tools.research.stage4_fleet_symbols import STAGE4_FIXED_FLEET_SYMBOLS, parse_symbol_list

        syms = parse_symbol_list("BTCUSDT,ETHUSDT,SOLUSDT,PEPEUSDT")
        self.assertEqual(syms, list(STAGE4_FIXED_FLEET_SYMBOLS))

    def test_fleet_stage3_context_uses_eth_seed_when_btc_listed_first(self) -> None:
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
                    symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT"],
                    mode="dry-run",
                    use_real_llm=True,
                )
            self.assertTrue(ok)
            self.assertEqual(reason, "")
            self.assertIsNone(summary)

    def test_per_symbol_summary_written(self) -> None:
        from tools.research.stage4_per_symbol_summary import build_per_symbol_summary

        decisions = [
            {
                "symbol": "BTCUSDT",
                "real_llm_used": True,
                "decision_intent": "hard_skip",
                "order_sent": False,
                "is_mock_ai": False,
                "parse_error": False,
            },
            {
                "symbol": "PEPEUSDT",
                "market_context_unavailable": True,
                "market_context_error": "symbol_unavailable_or_market_context_failed",
            },
        ]
        summary = build_per_symbol_summary(
            decisions,
            symbols_configured=["BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT"],
            symbols_with_market_context_error=["PEPEUSDT"],
        )
        self.assertIn("BTCUSDT", summary["symbols_seen"])
        self.assertIn("PEPEUSDT", summary["symbols_with_market_context_error"])
        self.assertEqual(summary["per_symbol"]["BTCUSDT"]["effective_decision_count"], 1)
        self.assertEqual(summary["per_symbol"]["PEPEUSDT"]["context_unavailable_count"], 1)
        self.assertIn("ETHUSDT", summary["symbols_missing"])

    def test_pepe_market_context_failure_recorded_safely(self) -> None:
        from tools.research.stage4_market_context import _empty_context, market_context_unavailable

        ctx = _empty_context("PEPEUSDT", limitations=["symbol_not_in_read_allowlist:PEPEUSDT"])
        bad, reason = market_context_unavailable(ctx)
        self.assertTrue(bad)
        self.assertEqual(reason, "symbol_unavailable_or_market_context_failed")

    def test_fleet_dry_run_once_missing_symbol_does_not_crash(self) -> None:
        import tempfile
        from unittest.mock import patch

        class FleetAgent:
            real_llm_used = True
            is_mock_ai = False
            model_name = "test-model"
            fallback_to_mock = False

            def decide(self, **kwargs):
                return {
                    "decision_id": "d1",
                    "created_at_utc": "2026-01-01T00:00:00Z",
                    "symbol": kwargs["symbol"].upper(),
                    "final_decision": "skip",
                    "final_action": "skip",
                    "decision_intent": "hard_skip",
                    "real_llm_used": True,
                    "is_mock_ai": False,
                    "order_sent": False,
                    "parse_error": False,
                    "risk_supervisor_result": {"approved": False, "final_decision": "skip"},
                    "market_context": kwargs["market_context"],
                    "account_context": kwargs["account_context"],
                }

        def fake_market(symbol: str):
            from tools.research.stage4_market_context import _empty_context

            if symbol.upper() == "PEPEUSDT":
                return _empty_context(symbol, limitations=["ticker_error:invalid"])
            return {
                "symbol": symbol.upper(),
                "last_price": 100.0,
                "regime": "range",
                "data_quality": "ok",
                "data_limitations": [],
            }

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "fleet_out"
            env = {
                "STAGE4_OUTPUT_DIR": str(out),
                "STAGE4_REQUIRE_STAGE3_CONTEXT": "false",
                "STAGE4_ALLOW_MOCK_FALLBACK": "true",
            }
            with patch.dict(os.environ, env, clear=False):
                from tools.research.run_stage4_ai_decision_dry_run import run_dry_run

                with patch(
                    "tools.research.run_stage4_ai_decision_dry_run.Stage4AIDecisionAgent",
                    return_value=FleetAgent(),
                ), patch(
                    "tools.research.run_stage4_ai_decision_dry_run._fetch_market",
                    side_effect=fake_market,
                ), patch(
                    "tools.research.run_stage4_ai_decision_dry_run._fetch_account",
                    return_value={"available_balance": 5000, "open_positions": 0},
                ), patch(
                    "tools.research.export_stage4_ai_decision_bundle.export_bundle",
                    return_value={"bundle_path": str(out / "b.tar.gz"), "bundle_safe": True, "file_count": 1},
                ):
                    summary = run_dry_run(
                        duration_minutes=0.01,
                        poll_interval_seconds=0,
                        symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT"],
                        mode="dry-run",
                        output_dir=out,
                        use_real_llm=False,
                    )
            self.assertIn("per_symbol", summary)
            self.assertIn("PEPEUSDT", summary.get("symbols_with_market_context_error") or [])
            self.assertEqual(summary.get("order_sent_count"), 0)
            self.assertEqual(summary.get("mock_ai_used_count"), 0)

    def test_shadow_compare_accepts_symbol_filter(self) -> None:
        from tools.research.stage4_shadow_compare import run_shadow_compare
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "ai_decisions.jsonl").write_text(
                json.dumps(
                    {
                        "decision_id": "x",
                        "created_at_utc": "2026-01-01T00:00:00Z",
                        "symbol": "BTCUSDT",
                        "final_decision": "skip",
                        "decision_intent": "hard_skip",
                        "confidence": 0.0,
                        "real_llm_used": True,
                        "is_mock_ai": False,
                        "order_sent": False,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            report = run_shadow_compare(
                decisions_dir=out,
                output_dir=out / "shadow",
                symbol="BTCUSDT",
                horizons_minutes=[15],
                kline_fetcher=lambda **kwargs: [],
            )
            self.assertEqual(report["summary"].get("decision_count"), 1)


class Stage413aEvidenceTests(unittest.TestCase):
    def test_per_symbol_chain_failed_matches_global_from_events(self) -> None:
        from tools.research.stage4_per_symbol_summary import build_per_symbol_summary

        decisions = [
            {"symbol": "BTCUSDT", "real_llm_used": True, "decision_intent": "watch", "order_sent": False},
            {"symbol": "ETHUSDT", "real_llm_used": True, "decision_intent": "hard_skip", "order_sent": False},
        ]
        events = [
            {"event_type": "provider_chain_failed", "symbol": "PEPEUSDT", "reason": "provider_chain_failed"},
            {"event_type": "provider_chain_failed", "symbol": "ETHUSDT", "reason": "provider_chain_failed"},
            {"event_type": "provider_chain_failed", "symbol": "SOLUSDT", "reason": "provider_chain_failed"},
            {"event_type": "provider_chain_failed", "symbol": "PEPEUSDT", "reason": "provider_chain_failed"},
        ]
        summary = build_per_symbol_summary(
            decisions,
            symbols_configured=["BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT"],
            system_events=events,
        )
        per_failed = {
            sym: int(row.get("provider_chain_failed_count") or 0)
            for sym, row in summary["per_symbol"].items()
        }
        self.assertEqual(per_failed["PEPEUSDT"], 2)
        self.assertEqual(per_failed["ETHUSDT"], 1)
        self.assertEqual(per_failed["SOLUSDT"], 1)
        self.assertEqual(sum(per_failed.values()), 4)

    def test_shadow_compare_filters_decisions_by_symbol(self) -> None:
        from tools.research.stage4_shadow_compare import run_shadow_compare
        import tempfile

        captured: list[str] = []

        def fake_klines(**kwargs):
            captured.append(str(kwargs.get("symbol")))
            return [
                {"start_ms": 1767225600000, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
            ]

        with tempfile.TemporaryDirectory() as tmp:
            dec_dir = Path(tmp) / "decisions"
            out_dir = Path(tmp) / "out"
            dec_dir.mkdir()
            rows = [
                {
                    "decision_id": "btc1",
                    "created_at_utc": "2026-01-01T00:00:00Z",
                    "symbol": "BTCUSDT",
                    "decision_intent": "watch",
                    "confidence": 0.2,
                    "real_llm_used": True,
                    "is_mock_ai": False,
                    "order_sent": False,
                    "market_context": {"last_price": 100.0, "regime": "range"},
                },
                {
                    "decision_id": "eth1",
                    "created_at_utc": "2026-01-01T00:05:00Z",
                    "symbol": "ETHUSDT",
                    "decision_intent": "hard_skip",
                    "confidence": 0.0,
                    "real_llm_used": True,
                    "is_mock_ai": False,
                    "order_sent": False,
                    "market_context": {"last_price": 200.0, "regime": "range"},
                },
            ]
            (dec_dir / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            report = run_shadow_compare(
                decisions_dir=dec_dir,
                output_dir=out_dir,
                symbol="BTCUSDT",
                horizons_minutes=[15],
                kline_fetcher=fake_klines,
            )
            self.assertEqual(report["summary"]["decision_count"], 1)
            self.assertEqual(report["summary"]["total_decision_count"], 2)
            self.assertEqual(captured, ["BTCUSDT"])

    def test_pepe_shadow_uses_1000pepe_market_alias(self) -> None:
        from tools.research.stage4_shadow_compare import run_shadow_compare
        import tempfile

        captured: list[str] = []

        def fake_klines(**kwargs):
            captured.append(str(kwargs.get("symbol")))
            return [
                {"start_ms": 1767225600000, "open": 0.01, "high": 0.011, "low": 0.009, "close": 0.0105},
            ]

        with tempfile.TemporaryDirectory() as tmp:
            dec_dir = Path(tmp) / "decisions"
            out_dir = Path(tmp) / "out"
            dec_dir.mkdir()
            (dec_dir / "ai_decisions.jsonl").write_text(
                json.dumps(
                    {
                        "decision_id": "pepe1",
                        "created_at_utc": "2026-01-01T00:00:00Z",
                        "symbol": "PEPEUSDT",
                        "decision_intent": "watch",
                        "confidence": 0.1,
                        "real_llm_used": True,
                        "is_mock_ai": False,
                        "order_sent": False,
                        "market_context": {"last_price": 0.01, "regime": "range"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            report = run_shadow_compare(
                decisions_dir=dec_dir,
                output_dir=out_dir,
                symbol="PEPEUSDT",
                horizons_minutes=[15],
                kline_fetcher=fake_klines,
            )
            summary = report["summary"]
            self.assertEqual(summary["requested_symbol"], "PEPEUSDT")
            self.assertEqual(summary["market_symbol"], "1000PEPEUSDT")
            self.assertTrue(summary["alias_used"])
            self.assertEqual(summary["decision_count"], 1)
            self.assertEqual(captured, ["1000PEPEUSDT"])

    def test_validator_detects_missing_decision_symbol(self) -> None:
        import tempfile
        from tools.research.validate_stage4_ai_decision_outputs import validate

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "ai_decisions.jsonl").write_text(
                json.dumps(
                    {
                        "decision_id": "x",
                        "created_at_utc": "2026-01-01T00:00:00Z",
                        "final_decision": "skip",
                        "decision_source": "ai_decision_agent",
                        "mode": "dry-run",
                        "model_name": "test",
                        "provider": "groq",
                        "decision_intent": "hard_skip",
                        "confidence": 0.0,
                        "real_llm_used": True,
                        "is_mock_ai": False,
                        "order_sent": False,
                        "parse_error": False,
                        "prompt_hash": "abc",
                        "market_context": {"last_price": 1.0},
                        "why_skip": "demo",
                        "confidence_reason": "demo",
                        "risk_supervisor_result": {"approved": False},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (out / "stage4_ai_decision_summary.json").write_text(
                json.dumps(
                    {
                        "dry_run_completed": True,
                        "effective_decision_count": 1,
                        "provider_chain_failed_count": 0,
                        "parse_error_count": 0,
                        "target_effective_decision_count": 1,
                    }
                ),
                encoding="utf-8",
            )
            (out / "llm_client_debug.jsonl").write_text('{"safe":true}\n', encoding="utf-8")
            result = validate(out, require_real_llm=True)
            self.assertGreater(result["decision_missing_symbol_count"], 0)
            self.assertFalse(result["validator_passed"])


class Stage413cRepairTests(unittest.TestCase):
    def test_parse_error_decision_not_counted_as_effective(self) -> None:
        from tools.research.stage4_per_symbol_summary import build_per_symbol_summary

        decisions = [
            {
                "symbol": "PEPEUSDT",
                "real_llm_used": True,
                "parse_error": True,
                "parse_error_type": "provider_invalid_json",
                "provider": "cerebras",
                "decision_id": "d1",
            },
            {
                "symbol": "BTCUSDT",
                "real_llm_used": True,
                "parse_error": False,
                "decision_intent": "watch",
                "provider": "groq",
            },
        ]
        summary = build_per_symbol_summary(decisions, symbols_configured=["BTCUSDT", "PEPEUSDT"])
        self.assertEqual(summary["per_symbol"]["PEPEUSDT"]["parse_error_count"], 1)
        self.assertEqual(summary["per_symbol"]["PEPEUSDT"]["effective_decision_count"], 0)
        self.assertEqual(summary["per_symbol"]["BTCUSDT"]["effective_decision_count"], 1)

    def test_parse_error_count_by_symbol_and_provider(self) -> None:
        from tools.research.stage4_parse_error_metrics import build_parse_error_summary

        decisions = [
            {
                "symbol": "PEPEUSDT",
                "parse_error": True,
                "parse_error_type": "provider_invalid_json",
                "provider": "cerebras",
                "decision_id": "a",
            },
            {
                "symbol": "ETHUSDT",
                "parse_error": True,
                "parse_error_type": "provider_response_truncated",
                "provider": "cerebras",
                "decision_id": "b",
            },
        ]
        metrics = build_parse_error_summary(decisions)
        self.assertEqual(metrics["parse_error_count"], 2)
        self.assertEqual(metrics["parse_error_count_by_symbol"]["PEPEUSDT"], 1)
        self.assertEqual(metrics["parse_error_count_by_provider"]["cerebras"], 2)
        self.assertEqual(len(metrics["parse_error_sample_refs"]), 2)

    def test_normalize_parse_error_types(self) -> None:
        from tools.research.stage4_parse_error_metrics import normalize_parse_error_type

        self.assertEqual(normalize_parse_error_type("json_decode_error"), "provider_invalid_json")
        self.assertEqual(normalize_parse_error_type("content_empty", raw_content_empty=True), "provider_empty_response")
        self.assertEqual(
            normalize_parse_error_type("missing_fields:x", raw_content_empty=False),
            "provider_schema_mismatch",
        )
        self.assertEqual(
            normalize_parse_error_type("provider_response_truncated", finish_reason="length"),
            "provider_response_truncated",
        )

    def test_validator_fails_when_parse_error_count_gt_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "ai_decisions.jsonl").write_text(
                json.dumps(
                    {
                        "decision_id": "x",
                        "created_at_utc": "2026-01-01T00:00:00Z",
                        "decision_source": "ai_decision_agent",
                        "mode": "dry_run",
                        "model_name": "llama-3.3-70b-versatile",
                        "provider": "cerebras",
                        "symbol": "PEPEUSDT",
                        "candidate_side": "NONE",
                        "final_action": "skip",
                        "confidence": 0.1,
                        "position_size_suggestion": 0,
                        "market_context": {"symbol": "PEPEUSDT"},
                        "account_context": {},
                        "retrieved_patches": [],
                        "recent_trade_results": [],
                        "recent_reflections": [],
                        "active_patch_count": 0,
                        "patch_applied_before_decision": False,
                        "current_open_positions": 0,
                        "why_enter": "",
                        "why_skip": "parse",
                        "side_reason": "x",
                        "confidence_reason": "x",
                        "risk_notes": [],
                        "patch_awareness": "",
                        "uncertainty": "",
                        "reasoning_summary": "",
                        "regime": "range",
                        "stage3_context_available": True,
                        "stage3_context_reason": "ok",
                        "recent_trade_results_count": 0,
                        "recent_reflections_count": 0,
                        "active_patches_count": 0,
                        "patch_blocked": False,
                        "parse_error": True,
                        "parse_error_type": "provider_invalid_json",
                        "safety_constraints": {},
                        "risk_supervisor_result": {"approved": False, "final_decision": "skip"},
                        "final_decision": "skip",
                        "order_sent": False,
                        "real_llm_used": True,
                        "is_mock_ai": False,
                        "prompt_hash": "abc",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (out / "risk_supervisor_decisions.jsonl").write_text("{}\n", encoding="utf-8")
            (out / "stage4_ai_decision_summary.json").write_text(
                json.dumps(
                    {
                        "dry_run_completed": True,
                        "effective_decision_count": 0,
                        "parse_error_count": 1,
                        "target_effective_decision_count": 1,
                        "provider_health_check_passed": True,
                    }
                ),
                encoding="utf-8",
            )
            (out / "llm_client_debug.jsonl").write_text('{"safe":true}\n', encoding="utf-8")
            from tools.research.validate_stage4_ai_decision_outputs import validate

            result = validate(out, require_real_llm=True)
            self.assertFalse(result["validator_passed"])
            self.assertGreater(result["parse_error_count"], 0)

    def test_expected_tick_count_180m_300s(self) -> None:
        from tools.research.stage4_tick_scheduler import expected_tick_count

        self.assertEqual(expected_tick_count(180, 300), 36)
        self.assertEqual(expected_tick_count(30, 300), 6)

    def test_tick_scheduler_absolute_sleep_not_fixed_drift(self) -> None:
        from tools.research.stage4_tick_scheduler import seconds_until_next_tick

        started = 1000.0
        with patch("tools.research.stage4_tick_scheduler.time.time", return_value=1045.0):
            sleep_for = seconds_until_next_tick(
                run_started_at=started,
                tick_index=1,
                poll_interval_seconds=300,
            )
        self.assertEqual(sleep_for, 255.0)

    def test_tick_drift_metrics_written(self) -> None:
        from tools.research.stage4_tick_scheduler import build_tick_scheduler_metrics

        metrics = build_tick_scheduler_metrics(
            duration_minutes=30,
            poll_interval_seconds=300,
            actual_tick_count=6,
            tick_processing_seconds=[12.0, 15.0],
            tick_drift_seconds=[0.0, 3.5],
        )
        self.assertEqual(metrics["expected_tick_count"], 6)
        self.assertEqual(metrics["actual_tick_count"], 6)
        self.assertEqual(metrics["tick_drift_seconds_max"], 3.5)
        self.assertEqual(metrics["tick_processing_seconds_max"], 15.0)

    def test_provider_chain_failed_attribution_still_matches_global(self) -> None:
        from tools.research.stage4_per_symbol_summary import build_per_symbol_summary, per_symbol_chain_failed_counts

        events = [
            {"event_type": "provider_chain_failed", "symbol": "ETHUSDT"},
            {"event_type": "provider_chain_failed", "symbol": "SOLUSDT"},
        ]
        summary = build_per_symbol_summary([], symbols_configured=["ETHUSDT", "SOLUSDT"], system_events=events)
        counts = per_symbol_chain_failed_counts(summary)
        self.assertEqual(sum(counts.values()), 2)

    def test_pepe_alias_shadow_still_works(self) -> None:
        from tools.research.stage4_fleet_symbols import fetch_symbol_for_market, market_symbol_info

        self.assertEqual(fetch_symbol_for_market("PEPEUSDT"), "1000PEPEUSDT")
        meta = market_symbol_info("PEPEUSDT")
        self.assertEqual(meta["market_symbol"], "1000PEPEUSDT")
        self.assertTrue(meta["alias_used"])

    def test_json_repair_parses_truncated_object(self) -> None:
        from tools.research.stage4_response_parser import parse_llm_response_text

        parsed, ok, err = parse_llm_response_text('{"final_action":"skip","confidence":0.2')
        self.assertTrue(ok)
        self.assertEqual(parsed.get("final_action"), "skip")
        self.assertEqual(err, "")

    def test_fleet_rate_gate_uses_shorter_default_interval(self) -> None:
        from tools.research.stage4_rate_limit_gate import Stage4LLMRateGate

        Stage4LLMRateGate.reset_shared()
        with patch.dict(
            os.environ,
            {"STAGE4_SYMBOLS": "BTCUSDT,ETHUSDT,SOLUSDT,PEPEUSDT"},
            clear=False,
        ):
            self.assertEqual(Stage4LLMRateGate.min_interval_seconds(), 6.0)
        Stage4LLMRateGate.reset_shared()

    def test_cerebras_default_max_tokens_1100(self) -> None:
        from tools.research.stage4_cerebras_payload import resolve_cerebras_max_tokens

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("STAGE4_CEREBRAS_MAX_TOKENS", None)
            self.assertEqual(resolve_cerebras_max_tokens(), 1100)


class Stage414aReviewTests(unittest.TestCase):
    def _summary_413d(self) -> dict:
        return {
            "duration_minutes": 180.0,
            "dry_run_completed": True,
            "effective_decision_count": 138,
            "target_effective_decision_count": 120,
            "parse_error_count": 0,
            "cerebras_parse_error_count": 0,
            "provider_chain_failed_count": 6,
            "skipped_tick_count": 6,
            "tick_count": 36,
            "expected_tick_count": 36,
            "tick_drift_seconds_max": 0.0,
            "symbols_configured": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT"],
            "provider_success_distribution": {"groq": 34, "cerebras": 104},
            "fallback_attempt_count": 110,
            "fallback_success_count": 110,
            "groq_cooldown_skip_count": 75,
            "groq_429_count": 3,
            "per_symbol": {
                "BTCUSDT": {"effective_decision_count": 36},
                "ETHUSDT": {"effective_decision_count": 34},
                "SOLUSDT": {"effective_decision_count": 33},
                "PEPEUSDT": {"effective_decision_count": 35},
            },
        }

    def test_provider_stability_review_detects_cerebras_dependency(self) -> None:
        from tools.research.stage4_provider_stability_review import build_provider_stability_review

        review = build_provider_stability_review(self._summary_413d())
        self.assertEqual(review["cerebras_share"], round(104 / 138, 4))
        self.assertIn("high_cerebras_dependency", review["stability_risks"])
        self.assertEqual(review["fallback_dependency_risk"], "high")
        self.assertTrue(review["needs_provider_budget_guard"])
        self.assertTrue(review["readiness_for_longer_run"])

    def test_shadow_quality_summary_fleet_aggregation(self) -> None:
        from tools.research.stage4_shadow_quality_summary import build_shadow_quality_summary

        per_symbol = {
            "BTCUSDT": {
                "requested_symbol": "BTCUSDT",
                "decision_count": 36,
                "shadow_compared_count": 36,
                "shadow_label_distribution": {
                    "neutral": 15,
                    "bad_watch": 12,
                    "missed_opportunity": 4,
                    "reasonable_watch": 3,
                    "good_skip": 2,
                },
                "decision_intent_distribution": {"watch": 32, "soft_skip": 4},
                "bad_watch_count": 12,
                "missed_opportunity_count": 4,
            },
            "ETHUSDT": {
                "requested_symbol": "ETHUSDT",
                "decision_count": 34,
                "shadow_compared_count": 34,
                "shadow_label_distribution": {
                    "neutral": 17,
                    "good_skip": 12,
                    "bad_watch": 3,
                    "missed_opportunity": 2,
                },
                "decision_intent_distribution": {"watch": 12, "hard_skip": 18, "soft_skip": 3, "enter_candidate": 1},
                "bad_watch_count": 3,
                "missed_opportunity_count": 2,
                "good_skip_count": 12,
            },
        }
        fleet = build_shadow_quality_summary(per_symbol)
        self.assertEqual(fleet["fleet_bad_watch_count"], 15)
        self.assertEqual(fleet["fleet_missed_opportunity_count"], 6)
        self.assertTrue(fleet["eth_relative_stability"])
        self.assertTrue(fleet["btc_bad_watch_elevated"])

    def test_analyze_label_by_intent(self) -> None:
        from tools.research.stage4_shadow_quality_summary import analyze_label_by_intent

        rows = [
            {"decision_intent": "watch", "shadow_label": "bad_watch"},
            {"decision_intent": "watch", "shadow_label": "bad_watch"},
            {"decision_intent": "hard_skip", "shadow_label": "missed_opportunity"},
        ]
        by_intent = analyze_label_by_intent(rows)
        self.assertEqual(by_intent["watch"]["bad_watch"], 2)
        self.assertEqual(by_intent["hard_skip"]["missed_opportunity"], 1)

    def test_multi_session_readiness_schema(self) -> None:
        from tools.research.stage4_multi_session_review import (
            build_414b_run_plan,
            build_multi_session_readiness,
        )

        readiness = build_multi_session_readiness(
            self._summary_413d(),
            session_id="stage4_413d_fixed_fleet_180m",
        )
        self.assertEqual(readiness["session_type"], "fixed_fleet_read_only")
        self.assertEqual(readiness["effective_decision_count"], 138)
        self.assertEqual(readiness["per_symbol_decision_counts"]["BTCUSDT"], 36)
        self.assertTrue(readiness["readiness_for_next_session"])

        plan = build_414b_run_plan()
        self.assertEqual(plan["duration_minutes"], 360)
        self.assertEqual(plan["expected_tick_count"], 72)
        self.assertEqual(plan["target_effective_decision_count"], 240)


class Stage414cRepairTests(unittest.TestCase):
    _VALID_LLM = {
        "final_action": "skip",
        "decision_intent": "watch",
        "symbol": "ETHUSDT",
        "candidate_side": "NONE",
        "confidence": 0.42,
        "why_enter": "",
        "why_skip": "No edge",
        "side_reason": "Flat",
        "confidence_reason": "Low",
        "risk_notes": [],
        "patch_awareness": "",
        "uncertainty": "medium",
        "requires_manual_review": False,
    }

    def test_cerebras_finish_reason_length_errors_even_when_json_repair_parses(self) -> None:
        from tools.research.stage4_llm_client import Stage4LLMClient, Stage4LLMConfig

        client = Stage4LLMClient(provider="cerebras", load_env=False)
        cfg = Stage4LLMConfig(provider="cerebras", model="gpt-oss-120b")
        result = client._finalize_cerebras_content(
            cfg,
            content='{"final_action":"skip","confidence":0.2',
            response_path="choices[0].message.content",
            finish_reason="length",
            http_status=200,
        )
        self.assertNotEqual(result.get("status"), "ok")
        self.assertEqual(result.get("error_type"), "provider_response_truncated")

    def test_cerebras_truncation_triggers_one_safe_retry_with_retry_max_tokens(self) -> None:
        from tools.research.stage4_llm_client import Stage4LLMClient, Stage4LLMConfig

        token_calls: List[int | None] = []

        def _fake_openai_compat(_self, _cfg, _messages, *, key_env, cerebras_max_tokens=None):
            token_calls.append(cerebras_max_tokens)
            if len(token_calls) == 1:
                return _self._error_result(
                    "provider_response_truncated",
                    error_type="provider_response_truncated",
                    provider="cerebras",
                    finish_reason="length",
                    response_text_chars=980,
                )
            return {
                "status": "ok",
                "provider": "cerebras",
                "parsed": dict(Stage414cRepairTests._VALID_LLM),
                "raw_text": json.dumps(Stage414cRepairTests._VALID_LLM),
                "finish_reason": "stop",
                "response_text_chars": 400,
            }

        with patch.dict(os.environ, {"CEREBRAS_API_KEY": "cerebras-test-key"}, clear=False), patch.object(
            Stage4LLMClient,
            "_openai_compat",
            _fake_openai_compat,
        ):
            client = Stage4LLMClient(provider="cerebras", load_env=False)
            client.cerebras_max_tokens = 1100
            client.cerebras_retry_max_tokens = 1400
            result = client.complete_json(
                [{"role": "user", "content": "decide"}],
                symbol="ETHUSDT",
                use_rate_gate=False,
            )

        self.assertEqual(result.get("status"), "ok")
        self.assertTrue(result.get("cerebras_truncation_retry"))
        self.assertTrue(result.get("cerebras_truncation_retry_success"))
        self.assertEqual(result.get("cerebras_max_tokens_retry"), 1400)
        self.assertEqual(len(token_calls), 2)
        self.assertEqual(token_calls[1], 1400)
        self.assertNotEqual(token_calls[0], 1400)

    def test_cerebras_retry_success_clears_parse_error_on_decision(self) -> None:
        class RetryLLM:
            provider_chain = ["cerebras"]

            def complete_json(self, messages, prompt_hash="", **kwargs):
                return {
                    "status": "ok",
                    "provider": "cerebras",
                    "model": "gpt-oss-120b",
                    "parsed": dict(Stage414cRepairTests._VALID_LLM),
                    "provider_chain": ["cerebras"],
                    "provider_attempts": [{"provider": "cerebras", "result": "success"}],
                    "cerebras_truncation_retry": True,
                    "cerebras_truncation_retry_success": True,
                    "cerebras_max_tokens_retry": 1400,
                    "finish_reason": "stop",
                }

        agent = Stage4AIDecisionAgent(use_real_llm=False, llm_client=RetryLLM())
        agent.real_llm_used = True
        agent.is_mock_ai = False
        agent.model_name = "gpt-oss-120b"
        decision = agent.decide(
            symbol="ETHUSDT",
            market_context={"last_price": 3250, "prev_price_24h": 3200},
            account_context={"available_balance": 5000},
        )
        self.assertFalse(decision.get("parse_error"))
        self.assertTrue(decision.get("cerebras_truncation_retry"))
        self.assertFalse(decision.get("order_sent"))

    def test_cerebras_retry_fail_keeps_parse_error_and_validator_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            bad = {
                "decision_id": "bad-1",
                "symbol": "ETHUSDT",
                "provider": "cerebras",
                "parse_error": True,
                "parse_error_type": "provider_response_truncated",
                "finish_reason": "length",
                "order_sent": False,
                "real_llm_used": True,
                "is_mock_ai": False,
                "cerebras_truncation_retry": True,
                "cerebras_truncation_retry_success": False,
                "provider_attempts": [{"provider": "cerebras", "result": "failed", "error_type": "provider_response_truncated"}],
            }
            append_jsonl(out / "ai_decisions.jsonl", bad)
            append_jsonl(out / "risk_supervisor_decisions.jsonl", {"decision_id": "bad-1", "approved": False})
            summary = {
                "dry_run_completed": True,
                "partial_completion": False,
                "effective_decision_count": 0,
                "target_effective_decision_count": 20,
                "parse_error_count": 1,
                "provider_success_distribution": {},
            }
            (out / "stage4_ai_decision_summary.json").write_text(json.dumps(summary), encoding="utf-8")
            from tools.research.validate_stage4_ai_decision_outputs import validate

            result = validate(out, require_real_llm=True)
            self.assertFalse(result.get("validator_passed"))
            self.assertFalse(result.get("technical_valid"))
            self.assertEqual(result.get("parse_error_count"), 1)

    def test_parse_error_not_counted_as_effective(self) -> None:
        from tools.research.run_stage4_ai_decision_dry_run import _empty_run_stats

        stats = _empty_run_stats()
        decision = {
            "parse_error": True,
            "parse_error_type": "provider_response_truncated",
            "symbol": "ETHUSDT",
            "cerebras_truncation_retry": True,
            "cerebras_truncation_retry_success": False,
        }
        if decision.get("parse_error"):
            stats["parse_error_count"] += 1
        else:
            stats["effective_decision_count"] += 1
        self.assertEqual(stats["effective_decision_count"], 0)
        self.assertEqual(stats["parse_error_count"], 1)

    def test_parse_error_metrics_by_symbol_and_provider(self) -> None:
        from tools.research.stage4_parse_error_metrics import build_parse_error_summary

        decisions = [
            {
                "parse_error": True,
                "parse_error_type": "provider_response_truncated",
                "symbol": "ETHUSDT",
                "provider": "cerebras",
                "decision_id": "x1",
            }
        ]
        metrics = build_parse_error_summary(decisions)
        self.assertEqual(metrics["parse_error_count"], 1)
        self.assertEqual(metrics["parse_error_count_by_symbol"]["ETHUSDT"], 1)
        self.assertEqual(metrics["parse_error_count_by_provider"]["cerebras"], 1)

    def test_provider_dependency_metrics_written(self) -> None:
        from tools.research.stage4_provider_metrics import build_provider_dependency_metrics

        metrics = build_provider_dependency_metrics(
            provider_success_distribution={"groq": 36, "cerebras": 249},
            cerebras_retry_count=1,
            cerebras_truncation_retry_success_count=1,
            cerebras_truncation_retry_fail_count=0,
        )
        self.assertEqual(metrics["provider_dependency_risk"], "high")
        self.assertEqual(metrics["primary_provider_success_ratio"], 0.126)
        self.assertEqual(metrics["secondary_provider_success_ratio"], 0.874)
        self.assertTrue(metrics["provider_budget_guard_active"])
        self.assertEqual(metrics["cerebras_truncation_retry_success_count"], 1)

    def test_cerebras_retry_respects_env_max_tokens(self) -> None:
        from tools.research.stage4_cerebras_payload import resolve_cerebras_retry_max_tokens

        with patch.dict(os.environ, {"STAGE4_CEREBRAS_RETRY_MAX_TOKENS": "1400"}, clear=False):
            self.assertEqual(resolve_cerebras_retry_max_tokens(), 1400)

    def test_debug_log_redacts_api_key_on_truncation_retry(self) -> None:
        from tools.research.stage4_response_parser import safe_excerpt

        leaked = safe_excerpt('{"error":"invalid key gsk-abcdefghijklmnopqrstuvwxyz1234567890"}')
        self.assertIn("[REDACTED]", leaked)
        self.assertNotIn("gsk-abcdefghijklmnopqrstuvwxyz1234567890", leaked)


class Stage414fRepairTests(unittest.TestCase):
    """Stage 4.14f provider schema mismatch safe repair."""

    _414D_NEAR_VALID = {
        "final_action": "skip",
        "decision_intent": "watch",
        "symbol": "BTCUSDT",
        "candidate_side": "NONE",
        "confidence": 0.32,
        "why_enter": "Modest 24h gain in range regime.",
        "why_skip": "No strong edge; monitor only.",
        "side_reason": "Flat bias.",
        "confidence_reason": "Moderate conviction.",
        "risk_notes": ["low volatility"],
        "patch_awareness": "none",
        "uncertainty": "moderate",
    }

    def test_414d_missing_requires_manual_review_cosmetic_repair(self) -> None:
        from tools.research.stage4_schema_repair import attempt_schema_safe_repair

        proposal, meta = attempt_schema_safe_repair(
            self._414D_NEAR_VALID,
            symbol="BTCUSDT",
            parse_error="missing_fields:requires_manual_review",
        )
        self.assertIsNotNone(proposal)
        self.assertTrue(meta.get("schema_repaired"))
        self.assertEqual(meta.get("schema_repair_mode"), "cosmetic_defaults")
        self.assertFalse(proposal.get("parse_error", True))
        self.assertEqual(proposal.get("final_action"), "skip")
        self.assertEqual(proposal.get("decision_intent"), "watch")
        self.assertEqual(proposal.get("confidence"), 0.32)
        self.assertFalse(proposal.get("requires_manual_review"))

    def test_safe_skip_repair_never_creates_enter(self) -> None:
        from tools.research.stage4_schema_repair import attempt_schema_safe_repair

        raw = {
            "final_action": "enter",
            "candidate_side": "BUY",
            "confidence": 0.8,
            "symbol": "ETHUSDT",
        }
        proposal, meta = attempt_schema_safe_repair(
            raw,
            symbol="ETHUSDT",
            parse_error="missing_fields:why_enter,why_skip",
        )
        self.assertIsNotNone(proposal)
        self.assertEqual(meta.get("schema_repair_mode"), "safe_skip_defaults")
        self.assertEqual(proposal.get("final_action"), "skip")
        self.assertEqual(proposal.get("decision_intent"), "hard_skip")
        self.assertEqual(proposal.get("confidence"), 0.0)
        self.assertEqual(proposal.get("candidate_side"), "NONE")
        self.assertEqual(proposal.get("position_size_suggestion"), 0.0)

    def test_unrecoverable_schema_remains_parse_error(self) -> None:
        from tools.research.stage4_schema_repair import attempt_schema_safe_repair

        proposal, meta = attempt_schema_safe_repair({}, symbol="BTCUSDT", parse_error="missing_fields:final_action")
        self.assertIsNone(proposal)
        self.assertTrue(meta.get("schema_mismatch_repair_fail"))

    def test_schema_mismatch_summary_metrics(self) -> None:
        from tools.research.stage4_schema_repair import build_schema_mismatch_summary

        decisions = [
            {
                "symbol": "BTCUSDT",
                "provider": "cerebras",
                "schema_repaired": True,
                "schema_mismatch_repair_attempted": True,
                "schema_repair_mode": "cosmetic_defaults",
                "parse_error": False,
            },
            {
                "symbol": "ETHUSDT",
                "provider": "cerebras",
                "parse_error": True,
                "parse_error_type": "provider_schema_mismatch",
                "schema_mismatch_repair_attempted": True,
            },
        ]
        metrics = build_schema_mismatch_summary(decisions)
        self.assertEqual(metrics["schema_mismatch_repair_success_count"], 1)
        self.assertEqual(metrics["schema_mismatch_repair_fail_count"], 1)
        self.assertEqual(metrics["schema_mismatch_count_by_symbol"]["ETHUSDT"], 1)
        self.assertEqual(metrics["schema_mismatch_count_by_provider"]["cerebras"], 1)

    def test_agent_applies_schema_repair_on_missing_field(self) -> None:
        class SchemaGapLLM:
            provider_chain = ["cerebras"]

            def complete_json(self, messages, prompt_hash="", **kwargs):
                return {
                    "status": "ok",
                    "provider": "cerebras",
                    "model": "gpt-oss-120b",
                    "parsed": dict(Stage414fRepairTests._414D_NEAR_VALID),
                    "provider_chain": ["cerebras"],
                    "provider_attempts": [{"provider": "cerebras", "result": "success"}],
                    "finish_reason": "stop",
                }

        agent = Stage4AIDecisionAgent(use_real_llm=False, llm_client=SchemaGapLLM())
        agent.real_llm_used = True
        agent.is_mock_ai = False
        agent.model_name = "gpt-oss-120b"
        decision = agent.decide(
            symbol="BTCUSDT",
            market_context={"last_price": 62500, "prev_price_24h": 62000, "symbol": "BTCUSDT"},
            account_context={"available_balance": 5000},
        )
        self.assertFalse(decision.get("parse_error"))
        self.assertTrue(decision.get("schema_repaired"))
        self.assertFalse(decision.get("order_sent"))


class Stage415QualityReviewTests(unittest.TestCase):
    def _write_session(
        self,
        root: Path,
        session_id: str,
        *,
        decisions: List[Dict[str, Any]],
        summary: Dict[str, Any],
        shadow_rows_by_symbol: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        shadow_template: Optional[str] = None,
    ) -> Dict[str, Any]:
        dec_dir = root / f"stage4_ai_decisions_{session_id}"
        dec_dir.mkdir(parents=True, exist_ok=True)
        jsonl = dec_dir / "ai_decisions.jsonl"
        jsonl.write_text("\n".join(json.dumps(d) for d in decisions) + "\n", encoding="utf-8")
        (dec_dir / "stage4_ai_decision_summary.json").write_text(json.dumps(summary), encoding="utf-8")
        session = {
            "session_id": session_id,
            "label": session_id,
            "decisions_dir": str(dec_dir),
            "shadow_symbol_template": shadow_template,
        }
        if shadow_template and shadow_rows_by_symbol:
            for sym, rows in shadow_rows_by_symbol.items():
                sh_dir = Path(shadow_template.format(symbol=sym))
                sh_dir.mkdir(parents=True, exist_ok=True)
                (sh_dir / "shadow_compare.jsonl").write_text(
                    "\n".join(json.dumps(r) for r in rows) + "\n",
                    encoding="utf-8",
                )
                labels = Counter(str(r.get("shadow_label") or "unknown") for r in rows)
                intents = Counter(str(r.get("decision_intent") or "unknown") for r in rows)
                compared = sum(1 for r in rows if r.get("shadow_label") != "insufficient_future_data")
                sh_summary = {
                    "requested_symbol": sym,
                    "decision_count": len(rows),
                    "shadow_compared_count": compared,
                    "shadow_label_distribution": dict(labels),
                    "decision_intent_distribution": dict(intents),
                    "bad_watch_count": labels.get("bad_watch", 0),
                    "missed_opportunity_count": labels.get("missed_opportunity", 0),
                }
                (sh_dir / "stage4_shadow_compare_summary.json").write_text(
                    json.dumps(sh_summary),
                    encoding="utf-8",
                )
        return session

    def test_quality_analyzer_loads_multiple_sessions(self) -> None:
        from tools.research.stage4_decision_quality_review import build_decision_quality_review

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d1 = {
                "symbol": "BTCUSDT",
                "decision_intent": "watch",
                "confidence": 0.4,
                "provider": "groq",
                "parse_error": False,
                "order_sent": False,
                "is_mock_ai": False,
            }
            d2 = dict(d1, symbol="ETHUSDT", decision_intent="hard_skip")
            s1 = self._write_session(
                root,
                "a",
                decisions=[d1],
                summary={
                    "effective_decision_count": 1,
                    "parse_error_count": 0,
                    "provider_success_distribution": {"groq": 1},
                    "mock_ai_used_count": 0,
                    "order_sent_count": 0,
                },
            )
            s2 = self._write_session(
                root,
                "b",
                decisions=[d2],
                summary={
                    "effective_decision_count": 1,
                    "parse_error_count": 0,
                    "provider_success_distribution": {"cerebras": 1},
                    "mock_ai_used_count": 0,
                    "order_sent_count": 0,
                },
            )
            for s in (s1, s2):
                s["decisions_dir"] = str(Path(s["decisions_dir"]))
            review = build_decision_quality_review([s1, s2], data_root=root)
            self.assertEqual(review["totals"]["total_effective_decisions"], 2)
            self.assertEqual(len(review["datasets_analyzed"]), 2)

    def test_per_symbol_quality_aggregation(self) -> None:
        from tools.research.stage4_decision_quality_review import build_decision_quality_review

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shadow = [
                {
                    "symbol": "SOLUSDT",
                    "decision_intent": "watch",
                    "shadow_label": "bad_watch",
                    "confidence": 0.55,
                    "provider": "cerebras",
                    "regime": "high_volatility",
                },
                {
                    "symbol": "SOLUSDT",
                    "decision_intent": "watch",
                    "shadow_label": "reasonable_watch",
                    "confidence": 0.35,
                    "provider": "groq",
                    "regime": "range",
                },
            ]
            session = self._write_session(
                root,
                "sh",
                decisions=[
                    {
                        "symbol": "SOLUSDT",
                        "decision_intent": "watch",
                        "confidence": 0.5,
                        "provider": "cerebras",
                        "parse_error": False,
                    }
                ],
                summary={
                    "effective_decision_count": 1,
                    "parse_error_count": 0,
                    "provider_success_distribution": {"cerebras": 1},
                    "mock_ai_used_count": 0,
                    "order_sent_count": 0,
                },
                shadow_rows_by_symbol={"SOLUSDT": shadow},
                shadow_template=str(root / "shadow_{symbol}"),
            )
            session["decisions_dir"] = str(Path(session["decisions_dir"]))
            session["shadow_symbol_template"] = str(root / "shadow_{symbol}")
            review = build_decision_quality_review([session], data_root=root)
            self.assertEqual(review["per_symbol_bad_watch_rate"]["SOLUSDT"], 0.5)
            self.assertEqual(review["per_symbol_reasonable_watch_rate"]["SOLUSDT"], 0.5)

    def test_bad_watch_and_missed_opportunity_rates(self) -> None:
        from tools.research.stage4_decision_quality_review import build_decision_quality_review

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                {"symbol": "PEPEUSDT", "decision_intent": "watch", "shadow_label": "bad_watch", "confidence": 0.6},
                {"symbol": "PEPEUSDT", "decision_intent": "hard_skip", "shadow_label": "missed_opportunity", "confidence": 0.2},
                {"symbol": "PEPEUSDT", "decision_intent": "hard_skip", "shadow_label": "good_skip", "confidence": 0.2},
                {"symbol": "PEPEUSDT", "decision_intent": "watch", "shadow_label": "neutral", "confidence": 0.3},
            ]
            session = self._write_session(
                root,
                "pepe",
                decisions=[{"symbol": "PEPEUSDT", "decision_intent": "watch", "provider": "groq", "parse_error": False}],
                summary={
                    "effective_decision_count": 1,
                    "parse_error_count": 0,
                    "provider_success_distribution": {"groq": 1},
                    "mock_ai_used_count": 0,
                    "order_sent_count": 0,
                },
                shadow_rows_by_symbol={"PEPEUSDT": rows},
                shadow_template=str(root / "shadow_{symbol}"),
            )
            session["decisions_dir"] = str(Path(session["decisions_dir"]))
            session["shadow_symbol_template"] = str(root / "shadow_{symbol}")
            review = build_decision_quality_review([session], data_root=root)
            self.assertEqual(review["per_symbol_bad_watch_rate"]["PEPEUSDT"], 0.25)
            self.assertEqual(review["per_symbol_missed_opportunity_rate"]["PEPEUSDT"], 0.25)
            self.assertEqual(review["per_symbol_good_skip_rate"]["PEPEUSDT"], 0.25)

    def test_intent_and_provider_dependency(self) -> None:
        from tools.research.stage4_decision_quality_review import build_decision_quality_review

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decisions = [
                {"symbol": "BTCUSDT", "decision_intent": "watch", "provider": "cerebras", "parse_error": False},
                {"symbol": "BTCUSDT", "decision_intent": "soft_skip", "provider": "cerebras", "parse_error": False},
                {"symbol": "ETHUSDT", "decision_intent": "hard_skip", "provider": "groq", "parse_error": False},
            ]
            session = self._write_session(
                root,
                "prov",
                decisions=decisions,
                summary={
                    "effective_decision_count": 3,
                    "parse_error_count": 0,
                    "provider_success_distribution": {"groq": 1, "cerebras": 2},
                    "mock_ai_used_count": 0,
                    "order_sent_count": 0,
                    "duration_minutes": 180,
                },
            )
            session["decisions_dir"] = str(Path(session["decisions_dir"]))
            review = build_decision_quality_review([session], data_root=root)
            self.assertEqual(review["intent_distribution_fleet"]["watch"], 1)
            self.assertEqual(review["provider_dependency_summary"]["cerebras_share"], round(2 / 3, 4))
            self.assertIn(review["provider_dependency_summary"]["provider_dependency_risk"], {"medium", "high", "low"})

    def test_report_writes_json_and_markdown(self) -> None:
        from tools.research.stage4_decision_quality_review import render_markdown_report, run_review

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = self._write_session(
                root,
                "out",
                decisions=[{"symbol": "BTCUSDT", "decision_intent": "watch", "provider": "groq", "parse_error": False}],
                summary={
                    "effective_decision_count": 1,
                    "parse_error_count": 0,
                    "provider_success_distribution": {"groq": 1},
                    "mock_ai_used_count": 0,
                    "order_sent_count": 0,
                },
            )
            session["decisions_dir"] = str(Path(session["decisions_dir"]))
            out_dir = root / "out_review"
            report = root / "report.md"
            summary = run_review(sessions=[session], output_dir=out_dir, report_path=report, data_root=root)
            self.assertTrue((out_dir / "stage4_15_decision_quality_summary.json").is_file())
            self.assertTrue(report.is_file())
            md = render_markdown_report(summary)
            self.assertIn("Stage 4.15", md)
            self.assertNotIn("sk-", md.lower())

    def test_no_order_no_mock_no_api_key_leak(self) -> None:
        from tools.research.stage4_decision_quality_review import build_decision_quality_review, render_markdown_report

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_key = "sk-" + "a" * 40
            session = self._write_session(
                root,
                "safe",
                decisions=[
                    {
                        "symbol": "BTCUSDT",
                        "decision_intent": "watch",
                        "provider": "groq",
                        "parse_error": False,
                        "order_sent": False,
                        "is_mock_ai": False,
                        "why_skip": f"should not leak {bad_key}",
                    }
                ],
                summary={
                    "effective_decision_count": 1,
                    "parse_error_count": 0,
                    "provider_success_distribution": {"groq": 1},
                    "mock_ai_used_count": 0,
                    "order_sent_count": 0,
                },
            )
            session["decisions_dir"] = str(Path(session["decisions_dir"]))
            review = build_decision_quality_review([session], data_root=root)
            self.assertEqual(review["order_sent_count"], 0)
            self.assertEqual(review["mock_ai_used_count"], 0)
            self.assertFalse(review["any_trading_action_sent"])
            md = render_markdown_report(review)
            self.assertNotIn(bad_key, md)


class Stage418CPaperReadinessSchemaTests(unittest.TestCase):
    def _base_llm(self, **overrides: Any) -> Dict[str, Any]:
        raw: Dict[str, Any] = {
            "final_action": "skip",
            "symbol": "BTCUSDT",
            "candidate_side": "NONE",
            "confidence": 0.45,
            "why_enter": "",
            "why_skip": "No edge",
            "side_reason": "Flat",
            "confidence_reason": "Low conviction",
            "risk_notes": [],
            "patch_awareness": "",
            "uncertainty": "medium",
            "requires_manual_review": False,
            "decision_intent": "watch",
        }
        raw.update(overrides)
        return raw

    def test_watch_requires_directional_bias(self) -> None:
        from tools.research.stage4_decision_schema import parse_llm_decision

        proposal, ok, _ = parse_llm_decision(self._base_llm(decision_intent="watch"), symbol="BTCUSDT")
        self.assertTrue(ok)
        self.assertTrue(proposal.get("decision_quality_incomplete"))

    def test_watch_with_directional_bias_paper_ready(self) -> None:
        from tools.research.stage4_decision_schema import parse_llm_decision

        proposal, ok, _ = parse_llm_decision(
            self._base_llm(
                decision_intent="watch",
                directional_bias="LONG",
                watch_confirmation_reason="Support held",
                invalidation={"invalidation_price": 61000, "invalidation_reason": "Break low", "max_adverse_move_pct": 0.3},
                mae_risk_estimate_pct=0.2,
            ),
            symbol="BTCUSDT",
        )
        self.assertTrue(ok)
        self.assertFalse(proposal.get("decision_quality_incomplete"))
        self.assertTrue(proposal.get("paper_readiness", {}).get("eligible_for_watchlist"))

    def test_enter_candidate_requires_candidate_side(self) -> None:
        from tools.research.stage4_decision_schema import parse_llm_decision

        proposal, ok, _ = parse_llm_decision(
            self._base_llm(
                decision_intent="enter_candidate",
                candidate_side="NONE",
                directional_bias="LONG",
                entry_trigger={"type": "pullback_confirm", "trigger_price": 62000, "trigger_condition": "VWAP"},
                invalidation={"invalidation_price": 61000, "invalidation_reason": "SL", "max_adverse_move_pct": 0.3},
                mae_risk_estimate_pct=0.2,
                risk_reward_estimate=1.5,
            ),
            symbol="BTCUSDT",
        )
        self.assertTrue(ok)
        self.assertTrue(proposal.get("decision_quality_incomplete"))

    def test_missing_directional_fields_not_parse_error(self) -> None:
        from tools.research.stage4_decision_schema import parse_llm_decision

        proposal, ok, err = parse_llm_decision(self._base_llm(decision_intent="watch"), symbol="BTCUSDT")
        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertFalse(proposal.get("parse_error"))

    def test_schema_repair_never_creates_trade_intent(self) -> None:
        from tools.research.stage4_schema_repair import attempt_schema_safe_repair

        raw = {
            "final_action": "enter",
            "symbol": "BTCUSDT",
            "candidate_side": "BUY",
            "confidence": 0.7,
        }
        proposal, meta = attempt_schema_safe_repair(
            raw, symbol="BTCUSDT", parse_error="missing_fields:why_enter"
        )
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.get("final_action"), "skip")
        self.assertEqual(proposal.get("decision_intent"), "hard_skip")
        self.assertEqual(proposal.get("candidate_side"), "NONE")

    def test_mae_risk_estimate_parsed(self) -> None:
        from tools.research.stage4_paper_readiness import parse_entry_trigger, parse_invalidation

        trigger = parse_entry_trigger({"type": "price_breakout", "trigger_price": 62000, "trigger_condition": "Break"})
        inv = parse_invalidation({"invalidation_price": 61000, "invalidation_reason": "SL", "max_adverse_move_pct": 0.25})
        self.assertEqual(trigger["type"], "price_breakout")
        self.assertEqual(inv["invalidation_reason"], "SL")

    def test_paper_readiness_metrics_in_summary(self) -> None:
        from tools.research.stage4_paper_readiness import build_paper_readiness_metrics

        metrics = build_paper_readiness_metrics(
            [
                {
                    "decision_intent": "watch",
                    "directional_bias": "LONG",
                    "watch_confirmation_reason": "ok",
                    "invalidation": {"invalidation_reason": "x", "invalidation_price": 1},
                    "mae_risk_estimate_pct": 0.2,
                    "decision_quality_incomplete": False,
                    "paper_readiness": {"eligible_for_watchlist": True, "eligible_for_hypothetical_entry": False},
                }
            ]
        )
        self.assertIn("paper_ready_watch_count", metrics)
        self.assertEqual(metrics["paper_ready_watch_count"], 1)

    def test_no_order_sent(self) -> None:
        agent = Stage4AIDecisionAgent(use_real_llm=False)
        decision = agent.decide(
            symbol="BTCUSDT",
            market_context={"last_price": 62000, "prev_price_24h": 61900},
            account_context={"available_balance": 5000},
        )
        self.assertFalse(decision.get("order_sent"))

    def test_no_exchange_path_in_agent(self) -> None:
        import tools.research.stage4_ai_decision_agent as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("urlopen", source)

    def test_production_btc_auto_not_referenced(self) -> None:
        import tools.research.stage4_decision_schema as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("btc-auto", source)
        self.assertNotIn("btc_auto", source)


if __name__ == "__main__":
    unittest.main()
