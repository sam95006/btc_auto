"""Server-side AI provider model-catalog probe (read-only, redacted).

Lists the model IDs each provider currently serves by calling its authenticated
`/models` endpoint with the service's own env-held key. Returns model IDs +
HTTP status only (no keys, no secrets) so a stale configured model can be
corrected against the provider's live catalog without moving a credential.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from config.llm_config import CEREBRAS_CHAT_COMPLETIONS_URL, GROQ_CHAT_COMPLETIONS_URL
from backend.nexus_private_cert.gemini_provider import GEMINI_API_BASE, GEMINI_ENV_KEY

_TIMEOUT = 20.0

# OpenAI-compat providers: (env key, /models endpoint) with Bearer auth.
_BEARER_PROVIDERS = {
    "groq": ("GROQ_API_KEY_PRIMARY", GROQ_CHAT_COMPLETIONS_URL.replace("/chat/completions", "/models")),
    "cerebras": ("CEREBRAS_API_KEY", CEREBRAS_CHAT_COMPLETIONS_URL.replace("/chat/completions", "/models")),
}


def _get(url: str, headers: dict[str, str]) -> tuple[int | None, Any]:
    try:
        req = Request(url, headers={"Accept": "application/json", **headers}, method="GET")
        with urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, None
    except Exception:  # noqa: BLE001
        return None, None


def _bearer_catalog(env_key: str, url: str) -> dict[str, Any]:
    key = os.environ.get(env_key)
    if not key:
        return {"status": "NOT_CONFIGURED", "http_status": None, "models": []}
    code, raw = _get(url, {"Authorization": f"Bearer {key}"})
    if code == 200 and isinstance(raw, dict):
        ids = sorted({str(m.get("id")) for m in (raw.get("data") or []) if isinstance(m, dict) and m.get("id")})
        return {"status": "OK", "http_status": 200, "models": ids}
    return {"status": "ERROR", "http_status": code, "models": []}


def _gemini_catalog() -> dict[str, Any]:
    key = os.environ.get(GEMINI_ENV_KEY)
    if not key:
        return {"status": "NOT_CONFIGURED", "http_status": None, "models": []}
    code, raw = _get(f"{GEMINI_API_BASE}/models", {"x-goog-api-key": key})
    if code == 200 and isinstance(raw, dict):
        ids = sorted({
            str(m.get("name")).replace("models/", "")
            for m in (raw.get("models") or []) if isinstance(m, dict) and m.get("name")
        })
        return {"status": "OK", "http_status": 200, "models": ids}
    return {"status": "ERROR", "http_status": code, "models": []}


def ai_model_catalog() -> dict[str, Any]:
    """Redacted per-provider available model IDs (no secret material)."""
    cat = {label: _bearer_catalog(env_key, url) for label, (env_key, url) in _BEARER_PROVIDERS.items()}
    cat["gemini"] = _gemini_catalog()
    return cat
