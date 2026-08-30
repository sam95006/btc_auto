"""Server-side AI provider model-catalog probe (read-only, redacted).

Lists the model IDs each provider currently serves by calling its authenticated
`/models` endpoint with the service's own env-held key. Returns model IDs only
(no keys, no secrets) so a stale configured model can be corrected against the
provider's live catalog without ever moving a credential outside the runtime.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.request import Request, urlopen

from config.llm_config import (
    CEREBRAS_CHAT_COMPLETIONS_URL,
    GROQ_CHAT_COMPLETIONS_URL,
    SAMBANOVA_CHAT_COMPLETIONS_URL,
)

_TIMEOUT = 20.0

# provider label -> (env key, models endpoint derived from the chat endpoint)
_PROVIDERS = {
    "groq": ("GROQ_API_KEY_PRIMARY", GROQ_CHAT_COMPLETIONS_URL.replace("/chat/completions", "/models")),
    "cerebras": ("CEREBRAS_API_KEY", CEREBRAS_CHAT_COMPLETIONS_URL.replace("/chat/completions", "/models")),
    "sambanova": ("SAMBANOVA_API_KEY", SAMBANOVA_CHAT_COMPLETIONS_URL.replace("/chat/completions", "/models")),
}


def _list_models(env_key: str, url: str) -> dict[str, Any]:
    key = os.environ.get(env_key)
    if not key:
        return {"status": "NOT_CONFIGURED", "models": []}
    try:
        req = Request(url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"}, method="GET")
        with urlopen(req, timeout=_TIMEOUT) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        data = raw.get("data") if isinstance(raw, dict) else None
        ids = sorted({str(m.get("id")) for m in (data or []) if isinstance(m, dict) and m.get("id")})
        return {"status": "OK", "models": ids}
    except Exception as exc:  # noqa: BLE001 - never leak internals/keys
        return {"status": "ERROR", "error": type(exc).__name__, "models": []}


def ai_model_catalog() -> dict[str, Any]:
    """Redacted per-provider available model IDs (no secret material)."""
    return {label: _list_models(env_key, url) for label, (env_key, url) in _PROVIDERS.items()}
