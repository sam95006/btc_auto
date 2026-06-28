"""Stage 4 AI Decision Layer tests — dry-run only, no orders."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.research.bybit_demo_client import BybitDemoClient
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

            def complete_json(self, messages, prompt_hash=""):
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
        self.assertEqual(result.veto_reason, "patch_block")

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
            def complete_json(self, messages, prompt_hash=""):
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
        decision = agent.decide(
            symbol="ETHUSDT",
            market_context={"last_price": 3250, "prev_price_24h": 3200},
            account_context={"available_balance": 5000},
        )
        self.assertFalse(decision.get("order_sent"))
        self.assertEqual(decision.get("final_decision"), "skip")
        self.assertTrue(decision.get("parse_error"))

    def test_rate_limit_retry_then_skip(self) -> None:
        class FlakyLLM:
            def availability(self):
                return {"real_llm_available": True}

            def complete_json(self, messages, prompt_hash=""):
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
        decision = agent.decide(
            symbol="ETHUSDT",
            market_context={"last_price": 3250, "prev_price_24h": 3200},
            account_context={"available_balance": 5000},
        )
        self.assertFalse(decision.get("order_sent"))

    def test_client_retries_rate_limit_then_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["STAGE4_OUTPUT_DIR"] = str(Path(tmp))
            try:
                from tools.research.stage4_llm_client import Stage4LLMClient, Stage4LLMConfig
                import urllib.error

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
                        raise urllib.error.HTTPError(url, 429, "rate", hdrs=None, fp=None)
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
            env.update({k: v for k, v in os.environ.items() if k not in ("GROQ_API_KEY", "GROQ_API_KEY_PRIMARY", "GROQ_API_KEY_SECONDARY")})
            with patch.dict(os.environ, env, clear=True):
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
