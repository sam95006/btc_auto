"""Native Google Gemini provider for the Founder AI gateway.

Speaks the native Gemini Developer API (generateContent), NOT the OpenAI-compat
shim. Used for the research-normalizer and independent-critic roles as a
no-new-paid-provider replacement for Cerebras/SambaNova.

Safety/privacy invariants:
- can_approve_order is always False. Only GROQ_MAIN_REASONER is order-critical;
  this provider can never submit/approve/cancel orders, change leverage, mutate
  positions, or bypass the Risk Engine / Cost Gate / safety gates.
- Every prompt passes through `redact_for_external` before leaving the runtime.
- The API key is read from GEMINI_API_KEY and sent ONLY via the x-goog-api-key
  header (never in a URL/query); it is never returned or logged.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.nexus_ai_gateway import coerce_to_schema, redact_for_external, validate_against_schema

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_ENV_KEY = "GEMINI_API_KEY"
# Role default models (overridable, low-latency structured Gemini models).
NORMALIZER_MODEL_ENV = "NEXUS_GEMINI_NORMALIZER_MODEL"
NORMALIZER_DEFAULT_MODEL = "gemini-2.5-flash-lite"
CRITIC_MODEL_ENV = "NEXUS_GEMINI_CRITIC_MODEL"
CRITIC_DEFAULT_MODEL = "gemini-2.5-flash"


@dataclass
class GeminiProvider:
    """Native Gemini adapter with the gateway's complete_json interface."""

    profile_id: str
    model_env: str
    default_model: str
    can_approve_order: bool = False  # hard invariant
    provider_name: str = "gemini"

    def model(self) -> str:
        return (os.environ.get(self.model_env) or self.default_model).strip()

    def is_configured(self) -> bool:
        return bool(os.environ.get(GEMINI_ENV_KEY))

    def complete_json(
        self,
        *,
        model_id: str | None = None,
        prompt: str,
        schema: dict[str, Any],
        timeout_s: float = 45.0,
    ) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
        api_key = os.environ.get(GEMINI_ENV_KEY)
        model = (model_id or self.model()).strip()
        if not api_key:
            return None, "PROVIDER_UNAVAILABLE", {"model_id": model, "smoke_map": "NOT_CONFIGURED"}
        redacted = redact_for_external(prompt)
        url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
        body = {
            "contents": [{"role": "user", "parts": [{"text": redacted}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1,
                "maxOutputTokens": 800,
                # Disable thinking for bounded low-latency structured work.
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        req = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-goog-api-key": api_key,  # never in URL/query
            },
            method="POST",
        )
        t0 = time.perf_counter()
        try:
            with urlopen(req, timeout=timeout_s) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            code = exc.code
            try:
                snippet = redact_for_external(exc.read().decode("utf-8", "ignore")[:200])
            except Exception:  # noqa: BLE001
                snippet = ""
            status = {400: "MODEL_UNAVAILABLE", 401: "PROVIDER_UNAVAILABLE", 403: "PROVIDER_UNAVAILABLE",
                      404: "MODEL_UNAVAILABLE", 429: "RATE_LIMITED"}.get(code, "PROVIDER_ERROR")
            smoke = {400: "MODEL_UNAVAILABLE", 401: "AUTH_FAILED", 403: "AUTH_FAILED",
                     404: "MODEL_UNAVAILABLE", 429: "RATE_LIMITED"}.get(code, "PROVIDER_ERROR")
            return None, status, {"model_id": model, "http_status": code, "smoke_map": smoke,
                                  "error_snippet_redacted": snippet}
        except TimeoutError:
            return None, "TIMEOUT", {"model_id": model, "smoke_map": "TIMEOUT"}
        except Exception as exc:  # noqa: BLE001
            return None, "UNKNOWN", {"model_id": model, "smoke_map": "PROVIDER_ERROR",
                                     "error_snippet_redacted": redact_for_external(str(exc)[:120])}

        latency = int((time.perf_counter() - t0) * 1000)
        try:
            text = (((raw.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}])[0].get("text") or ""
        except Exception:  # noqa: BLE001
            text = ""
        parsed = None
        if text:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                start, end = text.find("{"), text.rfind("}")
                if start >= 0 and end > start:
                    try:
                        parsed = json.loads(text[start : end + 1])
                    except json.JSONDecodeError:
                        parsed = None
        meta = {"model_id": model, "latency_ms": latency, "smoke_map": "REAL_API_PASS",
                "http_status": 200, "fingerprint": model, "endpoint_host": "generativelanguage.googleapis.com"}
        if parsed is None:
            return None, "INVALID_SCHEMA", {**meta, "smoke_map": "BAD_RESPONSE_SCHEMA"}
        coerced = coerce_to_schema(parsed, schema)
        if coerced is None or not validate_against_schema(coerced, schema):
            return None, "INVALID_SCHEMA", {**meta, "smoke_map": "BAD_RESPONSE_SCHEMA"}
        return coerced, "SUCCESS", meta
