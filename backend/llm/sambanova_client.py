import json
import os
import urllib.error
import urllib.request

from config.llm_config import DEFAULT_MAX_COMPLETION_TOKENS, DEFAULT_TIMEOUT_SECONDS, MODEL_FALLBACKS, SAMBANOVA_CHAT_COMPLETIONS_URL

from .structured_output_parser import parse_json_content


class SambaNovaLLMClient:
    def __init__(self, api_key_env: str, endpoint: str = SAMBANOVA_CHAT_COMPLETIONS_URL):
        self.api_key_env = api_key_env
        self.endpoint = endpoint

    def is_configured(self) -> bool:
        return bool(os.getenv(self.api_key_env))

    def _request(self, model: str, messages, temperature: float = 0.2):
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"missing_api_key:{self.api_key_env}")
        payload = {
            "model": model,
            "messages": list(messages or []),
            "temperature": min(max(temperature, 0.0), 1.0),
            "max_tokens": DEFAULT_MAX_COMPLETION_TOKENS,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 NEXUS/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            raw = json.loads(response.read().decode("utf-8"))
        return raw

    def complete_json(self, model: str, messages):
        model_chain = [model, *MODEL_FALLBACKS.get(model, [])]
        last_error = ""
        for candidate in model_chain:
            try:
                raw = self._request(candidate, messages)
                content = (((raw.get("choices") or [{}])[0].get("message") or {}).get("content")) or "{}"
                return {
                    "provider": "sambanova",
                    "model": candidate,
                    "raw_text": content,
                    "parsed": parse_json_content(content),
                    "status": "ok",
                    "error": "",
                }
            except urllib.error.HTTPError as exc:
                last_error = f"http_{exc.code}"
                if exc.code not in (400, 404, 410, 422):
                    break
            except Exception as exc:
                last_error = str(exc)
                break
        return {
            "provider": "sambanova",
            "model": model,
            "raw_text": "",
            "parsed": {},
            "status": "error",
            "error": last_error or "unknown_error",
        }
