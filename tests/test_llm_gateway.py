import unittest
from unittest.mock import patch

from backend.llm.llm_gateway import LLMGateway


class _FakeClient:
    def __init__(self, configured=True):
        self.configured = configured
        self.calls = []

    def is_configured(self):
        return self.configured

    def complete_json(self, model, messages):
        self.calls.append((model, messages))
        return {
            "provider": "fake",
            "model": model,
            "raw_text": '{"ok": true}',
            "parsed": {"ok": True, "model": model},
            "status": "ok",
            "error": "",
        }


class LLMGatewayTests(unittest.TestCase):
    def test_disabled_gateway_returns_disabled(self):
        gateway = LLMGateway()
        with patch("backend.llm.llm_gateway.llm_enabled", return_value=False):
            result = gateway.run_task("news", {"a": 1})
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["reason"], "llm_disabled")

    def test_routes_and_caches_news_requests(self):
        gateway = LLMGateway()
        fake = _FakeClient()
        gateway._clients["groq_primary"] = fake
        with patch("backend.llm.llm_gateway.llm_enabled", return_value=True):
            first = gateway.run_task("news", {"bucket_counts": {"crypto": 1}})
            second = gateway.run_task("news", {"bucket_counts": {"crypto": 1}})
        self.assertEqual(first["status"], "ok")
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(len(fake.calls), 1)

    def test_returns_disabled_when_provider_not_configured(self):
        gateway = LLMGateway()
        gateway._clients["sambanova"] = _FakeClient(configured=False)
        with patch("backend.llm.llm_gateway.llm_enabled", return_value=True):
            result = gateway.run_task("agent", {"world_channel": []})
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["reason"], "provider_not_configured")

    def test_provider_error_can_fallback_to_structured_output(self):
        class _ErrorClient(_FakeClient):
            def complete_json(self, model, messages):
                return {
                    "provider": "fake",
                    "model": model,
                    "raw_text": "",
                    "parsed": {},
                    "status": "error",
                    "error": "http_403",
                }

        gateway = LLMGateway()
        gateway._clients["groq_primary"] = _ErrorClient()
        with patch("backend.llm.llm_gateway.llm_enabled", return_value=True):
            result = gateway.run_task("news", {"bucket_counts": {"crypto": 1}}, fallback_output={"safe": True})
        self.assertEqual(result["status"], "fallback")
        self.assertEqual(result["output"], {"safe": True})


if __name__ == "__main__":
    unittest.main()
