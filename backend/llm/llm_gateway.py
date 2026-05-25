import hashlib
import json
import time

from config.llm_config import (
    ALLOWED_TASKS,
    PROVIDER_ENDPOINTS,
    PROVIDER_KEY_ENV,
    PROVIDER_LABELS,
    llm_enabled,
    task_model_defaults,
    task_provider_defaults,
    task_refresh_seconds,
)

from .groq_client import GroqLLMClient
from .prompt_templates import (
    build_agent_prompt,
    build_chat_prompt,
    build_news_prompt,
    build_radar_prompt,
    build_radar_proposal_prompt,
    build_reflection_prompt,
    build_roundtable_prompt,
    build_trade_proposer_prompt,
)
from .sambanova_client import SambaNovaLLMClient


class LLMGateway:
    def __init__(self):
        self._cache = {}
        self._clients = {
            "groq_primary": GroqLLMClient(PROVIDER_KEY_ENV["groq_primary"], endpoint=PROVIDER_ENDPOINTS["groq_primary"]),
            "groq_secondary": GroqLLMClient(PROVIDER_KEY_ENV["groq_secondary"], endpoint=PROVIDER_ENDPOINTS["groq_secondary"]),
            "sambanova": SambaNovaLLMClient(PROVIDER_KEY_ENV["sambanova"], endpoint=PROVIDER_ENDPOINTS["sambanova"]),
        }

    def enabled(self) -> bool:
        return bool(llm_enabled())

    def _fingerprint(self, payload: dict) -> str:
        blob = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def _build_prompt(self, task: str, payload: dict):
        if task == "news":
            return build_news_prompt(payload)
        if task == "radar":
            return build_radar_prompt(payload)
        if task == "radar_proposal":
            return build_radar_proposal_prompt(payload)
        if task == "roundtable":
            return build_roundtable_prompt(payload)
        if task == "reflection":
            return build_reflection_prompt(payload)
        if task == "agent":
            return build_agent_prompt(payload)
        if task == "chat":
            return build_chat_prompt(payload)
        if task == "trade_proposer":
            return build_trade_proposer_prompt(payload)
        raise ValueError(f"unsupported_task:{task}")

    def _client_for_task(self, task: str):
        provider_key = task_provider_defaults().get(task, "disabled")
        return provider_key, self._clients.get(provider_key)

    def run_task(self, task: str, payload: dict, fallback_output=None):
        if task not in ALLOWED_TASKS:
            return {"status": "disabled", "reason": "unsupported_task", "task": task}
        if not self.enabled():
            return {"status": "disabled", "reason": "llm_disabled", "task": task, "output": fallback_output or {}}

        fingerprint = self._fingerprint(payload)
        cache_key = f"{task}:{fingerprint}"
        refresh_after = task_refresh_seconds().get(task, 60)
        cached = self._cache.get(cache_key)
        if cached and (time.time() - cached["created_at"]) < refresh_after:
            return {**cached["result"], "cache_hit": True}

        provider_key, client = self._client_for_task(task)
        if not client or not client.is_configured():
            result = {
                "task": task,
                "status": "disabled",
                "provider": provider_key,
                "reason": "provider_not_configured",
                "cache_hit": False,
                "output": fallback_output or {},
            }
            self._cache[cache_key] = {"created_at": time.time(), "result": result}
            return result

        prompt = self._build_prompt(task, payload)
        task_models = task_model_defaults()
        model = task_models["agent_fallback"] if task == "agent_fallback" else task_models.get(task, "")
        response = client.complete_json(model, prompt)
        result = {
            "task": task,
            "status": response.get("status", "error"),
            "provider": PROVIDER_LABELS.get(provider_key, provider_key),
            "provider_key": provider_key,
            "model": response.get("model", model),
            "error": response.get("error", ""),
            "cache_hit": False,
            "fingerprint": fingerprint,
            "generated_at": int(time.time() * 1000),
            "output": response.get("parsed", {}),
        }
        if result["status"] != "ok" and fallback_output is not None:
            result["status"] = "fallback"
            result["output"] = fallback_output
        self._cache[cache_key] = {"created_at": time.time(), "result": result}
        return result

    def status_snapshot(self):
        provider_status = {}
        for name, client in self._clients.items():
            provider_status[name] = {
                "configured": client.is_configured(),
                "provider": PROVIDER_LABELS.get(name, name),
            }
        return {
            "enabled": self.enabled(),
            "providers": provider_status,
            "routes": task_provider_defaults(),
            "models": task_model_defaults(),
            "cache_entries": len(self._cache),
        }
