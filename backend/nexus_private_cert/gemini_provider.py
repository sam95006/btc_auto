"""Dedicated Google Gemini critic adapter (native Gemini Developer API).

Used as GEMINI_INDEPENDENT_CRITIC for PRIVATE-ENV-2 certification. It is NOT
routed through the OpenAI-compat / SambaNova code path — it speaks the native
generateContent contract.

Hard guarantees:
- Read-only critique only: can_approve_order = False. It cannot submit/approve
  orders, modify risk, bypass the Risk Engine, mutate positions, change
  leverage, or change trading policy.
- Privacy: every prompt passes through the existing external-provider
  redaction boundary (`redact_for_external`) before it leaves the runtime, so
  no key/secret/DSN/account identity/private wallet data/strategy secret is
  sent to Gemini.
- The API key is read from env (GEMINI_API_KEY), sent only in the
  `x-goog-api-key` header (never in a URL/query), and never returned or logged.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.nexus_ai_gateway import coerce_to_schema, redact_for_external, validate_against_schema

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_ENV_KEY = "GEMINI_API_KEY"
GEMINI_MODEL_ENV = "NEXUS_GEMINI_CRITIC_MODEL"
GEMINI_DEFAULT_MODEL = "gemini-3.7-flash"
PROFILE_ID = "GEMINI_INDEPENDENT_CRITIC"


def gemini_model() -> str:
    return (os.environ.get(GEMINI_MODEL_ENV) or GEMINI_DEFAULT_MODEL).strip()


class GeminiCriticProvider:
    """Independent reflection critic. Cannot approve or influence orders."""

    provider_name = "gemini"
    can_approve_order = False  # hard invariant

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
        model = (model_id or gemini_model()).strip()
        if not api_key:
            return None, "NOT_CONFIGURED", {"model_id": model, "smoke_map": "NOT_CONFIGURED"}
        # Redaction boundary: never send raw content to Gemini.
        redacted = redact_for_external(prompt)
        url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
        body = {
            "contents": [{"role": "user", "parts": [{"text": redacted}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1,
                "maxOutputTokens": 800,
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
            snippet = ""
            try:
                snippet = redact_for_external(exc.read().decode("utf-8", "ignore")[:200])
            except Exception:  # noqa: BLE001
                snippet = ""
            status = {
                400: "MODEL_UNAVAILABLE",
                401: "AUTH_FAILED",
                403: "AUTH_FAILED",
                404: "MODEL_UNAVAILABLE",
                429: "RATE_LIMITED",
            }.get(code, "PROVIDER_ERROR")
            return None, status, {"model_id": model, "http_status": code, "smoke_map": status, "error": snippet}
        except TimeoutError:
            return None, "TIMEOUT", {"model_id": model, "smoke_map": "TIMEOUT"}
        except Exception as exc:  # noqa: BLE001
            return None, "PROVIDER_ERROR", {
                "model_id": model, "smoke_map": "PROVIDER_ERROR",
                "error": redact_for_external(str(exc)[:120]),
            }

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
        meta = {"model_id": model, "latency_ms": latency, "smoke_map": "REAL_API_PASS", "http_status": 200}
        if parsed is None:
            return None, "INVALID_SCHEMA", {**meta, "smoke_map": "BAD_RESPONSE_SCHEMA"}
        coerced = coerce_to_schema(parsed, schema)
        if coerced is None or not validate_against_schema(coerced, schema):
            return None, "INVALID_SCHEMA", {**meta, "smoke_map": "BAD_RESPONSE_SCHEMA"}
        return coerced, "SUCCESS", meta


def gemini_smoke() -> dict[str, Any]:
    """One minimal sanitized structured smoke. No secret/account/strategy data."""
    schema = {"title": "nexus_smoke_v1", "required": ["ok", "ping"],
              "properties": {"ok": {"type": "boolean"}, "ping": {"type": "string"}}}
    prompt = 'Return JSON {"ok": true, "ping": "pong"} only. No secrets, no account data, no strategy.'
    provider = GeminiCriticProvider()
    if not provider.is_configured():
        return {"result_status": "NOT_CONFIGURED", "http_status": None, "smoke_map": "NOT_CONFIGURED",
                "verified_model_id": gemini_model(), "can_approve_order": False}
    parsed, status, meta = provider.complete_json(prompt=prompt, schema=schema)
    result = "REAL_API_PASS" if status == "SUCCESS" else meta.get("smoke_map", status)
    return {
        "result_status": result,
        "http_status": meta.get("http_status"),
        "smoke_map": meta.get("smoke_map"),
        "verified_model_id": meta.get("model_id"),
        "error": meta.get("error"),
        "can_approve_order": False,
    }
