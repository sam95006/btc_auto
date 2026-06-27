"""Stage 4 LLM client — trusted non-China providers only; dry-run decisions."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]

BLOCKED_MODEL_PATTERNS = re.compile(
    r"(deepseek|qwen|chatglm|glm-|baichuan|yi-|moonshot|kimi|doubao|spark|minimax|ernie|wenxin|hunyuan|zhipu)",
    re.IGNORECASE,
)

OPENAI_COMPAT_URLS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "ollama": None,
}

DEFAULT_MODELS = {
    "groq": os.environ.get("STAGE4_LLM_MODEL", "llama-3.3-70b-versatile"),
    "openai": os.environ.get("STAGE4_LLM_MODEL", "gpt-4o-mini"),
    "anthropic": os.environ.get("STAGE4_LLM_MODEL", "claude-3-5-haiku-20241022"),
    "gemini": os.environ.get("STAGE4_LLM_MODEL", "gemini-2.0-flash"),
    "ollama": os.environ.get("STAGE4_LLM_MODEL", "llama3.3"),
    "cerebras": os.environ.get("STAGE4_LLM_MODEL", "llama-3.3-70b"),
}


def _load_local_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _model_allowed(model: str) -> bool:
    return not BLOCKED_MODEL_PATTERNS.search(model or "")


def _http_post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


@dataclass
class Stage4LLMConfig:
    provider: str
    model: str
    api_key_env: str = ""
    endpoint: str = ""


class Stage4LLMClient:
    """Resolve and call an allowed LLM provider for structured JSON decisions."""

    def __init__(self, *, provider: str = "", model: str = "", load_env: bool = True) -> None:
        if load_env:
            _load_local_env()
        self.timeout = int(os.environ.get("NEXUS_LLM_TIMEOUT_SECONDS", "12"))
        self.max_tokens = int(os.environ.get("NEXUS_LLM_MAX_COMPLETION_TOKENS", "700"))
        self.config = self._resolve_config(provider=provider, model=model)
        self.available = self.config is not None and self._provider_ready(self.config)

    def _resolve_config(self, *, provider: str, model: str) -> Optional[Stage4LLMConfig]:
        explicit = (provider or os.environ.get("STAGE4_LLM_PROVIDER", "auto")).strip().lower()
        candidates: List[Tuple[str, str, str, str]] = []
        if explicit != "auto":
            candidates.append((explicit, model, "", ""))
        else:
            for prov, key_env, endpoint in (
                ("groq", "GROQ_API_KEY_PRIMARY", OPENAI_COMPAT_URLS["groq"]),
                ("openai", "OPENAI_API_KEY", OPENAI_COMPAT_URLS["openai"]),
                ("anthropic", "ANTHROPIC_API_KEY", "https://api.anthropic.com/v1/messages"),
                ("gemini", "GOOGLE_API_KEY", "https://generativelanguage.googleapis.com/v1beta/models"),
                ("cerebras", "CEREBRAS_API_KEY", "https://api.cerebras.ai/v1/chat/completions"),
                ("ollama", "", ""),
            ):
                candidates.append((prov, model, key_env, endpoint))

        for prov, mdl, key_env, endpoint in candidates:
            chosen_model = mdl or DEFAULT_MODELS.get(prov, "")
            if not _model_allowed(chosen_model):
                continue
            if prov == "ollama":
                base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
                if base:
                    return Stage4LLMConfig(provider=prov, model=chosen_model, endpoint=base)
                continue
            if key_env and os.environ.get(key_env):
                return Stage4LLMConfig(provider=prov, model=chosen_model, api_key_env=key_env, endpoint=endpoint)
        return None

    def _provider_ready(self, cfg: Stage4LLMConfig) -> bool:
        if cfg.provider == "ollama":
            return bool(cfg.endpoint)
        return bool(cfg.api_key_env and os.environ.get(cfg.api_key_env))

    def availability(self) -> Dict[str, Any]:
        if not self.config or not self.available:
            return {
                "real_llm_available": False,
                "real_llm_unavailable": True,
                "provider": None,
                "model_name": None,
                "reason": "no_allowed_provider_configured",
            }
        return {
            "real_llm_available": True,
            "real_llm_unavailable": False,
            "provider": self.config.provider,
            "model_name": self.config.model,
            "reason": "",
        }

    def complete_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        if not self.available or not self.config:
            return {"status": "error", "error": "llm_unavailable", "parsed": {}, "raw_text": ""}

        cfg = self.config
        try:
            if cfg.provider in {"groq", "openai", "cerebras"}:
                return self._openai_compat(cfg, messages)
            if cfg.provider == "anthropic":
                return self._anthropic(cfg, messages)
            if cfg.provider == "gemini":
                return self._gemini(cfg, messages)
            if cfg.provider == "ollama":
                return self._ollama(cfg, messages)
        except Exception as exc:
            return {"status": "error", "error": str(exc)[:200], "parsed": {}, "raw_text": ""}
        return {"status": "error", "error": "unsupported_provider", "parsed": {}, "raw_text": ""}

    def _openai_compat(self, cfg: Stage4LLMConfig, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        url = cfg.endpoint
        if cfg.provider == "cerebras":
            url = cfg.endpoint
        key = os.environ.get(cfg.api_key_env, "")
        payload = {
            "model": cfg.model,
            "messages": messages,
            "temperature": 0.2,
            "max_completion_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        raw = _http_post_json(
            url,
            {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            payload,
            self.timeout,
        )
        content = (((raw.get("choices") or [{}])[0].get("message") or {}).get("content")) or "{}"
        parsed = self._parse_json(content)
        return {
            "status": "ok" if parsed else "error",
            "provider": cfg.provider,
            "model": cfg.model,
            "raw_text": content,
            "parsed": parsed,
            "error": "" if parsed else "json_parse_failed",
        }

    def _anthropic(self, cfg: Stage4LLMConfig, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        system = next((m["content"] for m in messages if m.get("role") == "system"), "")
        user_parts = [m["content"] for m in messages if m.get("role") == "user"]
        payload = {
            "model": cfg.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": "\n".join(user_parts)}],
        }
        raw = _http_post_json(
            cfg.endpoint,
            {
                "x-api-key": os.environ.get(cfg.api_key_env, ""),
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            payload,
            self.timeout,
        )
        blocks = raw.get("content") or []
        content = next((b.get("text") for b in blocks if b.get("type") == "text"), "{}")
        parsed = self._parse_json(content)
        return {
            "status": "ok" if parsed else "error",
            "provider": cfg.provider,
            "model": cfg.model,
            "raw_text": content,
            "parsed": parsed,
            "error": "" if parsed else "json_parse_failed",
        }

    def _gemini(self, cfg: Stage4LLMConfig, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        key = os.environ.get(cfg.api_key_env, "")
        prompt = "\n".join(m["content"] for m in messages)
        url = f"{cfg.endpoint}/{cfg.model}:generateContent?key={key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        raw = _http_post_json(url, {"Content-Type": "application/json"}, payload, self.timeout)
        parts = (((raw.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
        content = parts[0].get("text") if parts else "{}"
        parsed = self._parse_json(content)
        return {
            "status": "ok" if parsed else "error",
            "provider": cfg.provider,
            "model": cfg.model,
            "raw_text": content,
            "parsed": parsed,
            "error": "" if parsed else "json_parse_failed",
        }

    def _ollama(self, cfg: Stage4LLMConfig, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        url = f"{cfg.endpoint.rstrip('/')}/api/chat"
        payload = {
            "model": cfg.model,
            "messages": messages,
            "stream": False,
            "format": "json",
        }
        raw = _http_post_json(url, {"Content-Type": "application/json"}, payload, self.timeout)
        content = (raw.get("message") or {}).get("content") or "{}"
        parsed = self._parse_json(content)
        return {
            "status": "ok" if parsed else "error",
            "provider": cfg.provider,
            "model": cfg.model,
            "raw_text": content,
            "parsed": parsed,
            "error": "" if parsed else "json_parse_failed",
        }

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        from backend.llm.structured_output_parser import parse_json_content

        parsed = parse_json_content(text)
        return parsed if isinstance(parsed, dict) else {}
