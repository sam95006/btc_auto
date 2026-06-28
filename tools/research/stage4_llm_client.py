"""Stage 4 LLM client — trusted non-China providers; dry-run decisions."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tools.research.bybit_demo_learning_common import utc_now_iso
from tools.research.stage4_response_parser import (
    extract_anthropic_content,
    extract_gemini_content,
    extract_ollama_content,
    extract_openai_compat_content,
    parse_llm_response_text,
    safe_excerpt,
)

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

GROQ_KEY_ENVS = ("GROQ_API_KEY_PRIMARY", "GROQ_API_KEY_SECONDARY", "GROQ_API_KEY")


def _first_env_key(names: Tuple[str, ...]) -> str:
    for name in names:
        if os.environ.get(name):
            return name
    return ""

RETRYABLE_HTTP = frozenset({408, 429, 500, 502, 503, 504})
MAX_RETRIES = 2
BACKOFF_SECONDS = (1.0, 2.5)

HTTP_HEADERS_BASE = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 NEXUS-Stage4/1.0",
}


def _bridge_groq_env_aliases() -> None:
    """Mirror Zeabur GROQ_API_KEY into PRIMARY when only legacy name is set."""
    groq = (os.environ.get("GROQ_API_KEY") or "").strip()
    primary = (os.environ.get("GROQ_API_KEY_PRIMARY") or "").strip()
    if groq and not primary:
        os.environ["GROQ_API_KEY_PRIMARY"] = groq
    elif primary and not groq:
        os.environ["GROQ_API_KEY"] = primary


class RealLLMRequiredError(RuntimeError):
    """Raised when real LLM is required but unavailable (no mock fallback)."""

    def __init__(self, reason: str = "missing_real_llm_key") -> None:
        self.reason = reason
        super().__init__(reason)


def env_truthy(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def require_real_llm_enabled() -> bool:
    return env_truthy("STAGE4_REQUIRE_REAL_LLM", False)


def mock_fallback_allowed(*, use_real_llm: bool = True) -> bool:
    if not use_real_llm:
        return True
    if require_real_llm_enabled():
        return env_truthy("STAGE4_ALLOW_MOCK_FALLBACK", False)
    return env_truthy("STAGE4_ALLOW_MOCK_FALLBACK", True)


def groq_key_configured() -> bool:
    _bridge_groq_env_aliases()
    return bool(_first_env_key(GROQ_KEY_ENVS))


def groq_key_status() -> Dict[str, Any]:
    _bridge_groq_env_aliases()
    used = _first_env_key(GROQ_KEY_ENVS)
    present_names = [name for name in GROQ_KEY_ENVS if os.environ.get(name)]
    return {
        "groq_key_aliases_checked": list(GROQ_KEY_ENVS),
        "groq_key_present": bool(present_names),
        "groq_key_env_used": used or None,
        "groq_key_env_count": len(present_names),
    }


def real_llm_preflight(*, use_real_llm: bool, provider: str = "", model: str = "") -> Tuple[bool, str]:
    if not use_real_llm:
        return True, ""
    if mock_fallback_allowed(use_real_llm=True):
        return True, ""
    if not groq_key_configured():
        return False, "missing_real_llm_key"
    prov = (provider or os.environ.get("STAGE4_LLM_PROVIDER", "groq") or "groq").strip().lower()
    mdl = (model or os.environ.get("STAGE4_LLM_MODEL", "") or "").strip()
    client = Stage4LLMClient(provider=prov, model=mdl, load_env=True)
    avail = client.availability()
    if not avail.get("real_llm_available"):
        return False, str(avail.get("reason") or "no_allowed_provider_configured")
    return True, ""


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


def resolve_debug_log_path() -> Path:
    import os as _os

    custom = _os.environ.get("STAGE4_OUTPUT_DIR", "").strip()
    if custom:
        out = Path(custom)
    else:
        nexus = _os.environ.get("NEXUS_DATA_DIR", "").strip()
        if nexus:
            candidate = Path(nexus) / "stage4_ai_decisions"
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                probe = candidate / ".write_probe"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink(missing_ok=True)
                out = candidate
            except OSError:
                out = ROOT / "data" / "external_alpha" / "stage4_ai_decisions"
        else:
            out = ROOT / "data" / "external_alpha" / "stage4_ai_decisions"
    out.mkdir(parents=True, exist_ok=True)
    return out / "llm_client_debug.jsonl"


def append_debug_log(row: Dict[str, Any]) -> None:
    safe_row = dict(row)
    for key in ("error_message_safe", "raw_content_excerpt", "error"):
        if key in safe_row and safe_row[key]:
            safe_row[key] = safe_excerpt(str(safe_row[key]))
    path = resolve_debug_log_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(safe_row, ensure_ascii=False) + "\n")


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
        _bridge_groq_env_aliases()
        self.timeout = int(os.environ.get("NEXUS_LLM_TIMEOUT_SECONDS", "20"))
        self.max_tokens = int(os.environ.get("NEXUS_LLM_MAX_COMPLETION_TOKENS", "700"))
        self.config = self._resolve_config(provider=provider, model=model)
        self.available = self.config is not None and self._provider_ready(self.config)

    def _resolve_config(self, *, provider: str, model: str) -> Optional[Stage4LLMConfig]:
        explicit = (provider or os.environ.get("STAGE4_LLM_PROVIDER", "auto")).strip().lower()
        provider_defaults = {
            "groq": ("GROQ_API_KEY_PRIMARY", OPENAI_COMPAT_URLS["groq"]),
            "openai": ("OPENAI_API_KEY", OPENAI_COMPAT_URLS["openai"]),
            "anthropic": ("ANTHROPIC_API_KEY", "https://api.anthropic.com/v1/messages"),
            "gemini": ("GOOGLE_API_KEY", "https://generativelanguage.googleapis.com/v1beta/models"),
            "cerebras": ("CEREBRAS_API_KEY", "https://api.cerebras.ai/v1/chat/completions"),
            "ollama": ("", ""),
        }
        candidates: List[Tuple[str, str, str, str]] = []
        if explicit != "auto":
            key_env, endpoint = provider_defaults.get(explicit, ("", ""))
            if explicit == "groq":
                key_env = _first_env_key(GROQ_KEY_ENVS)
            candidates.append((explicit, model, key_env, endpoint))
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
            if prov == "groq":
                key_env = _first_env_key(GROQ_KEY_ENVS)
                if not key_env:
                    continue
            elif not (key_env and os.environ.get(key_env)):
                continue
            if key_env:
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

    def complete_json(
        self,
        messages: List[Dict[str, str]],
        *,
        prompt_hash: str = "",
    ) -> Dict[str, Any]:
        if not self.available or not self.config:
            return self._error_result("llm_unavailable", error_type="llm_unavailable")

        cfg = self.config
        key_chain = self._api_key_chain(cfg)
        last_result: Dict[str, Any] = self._error_result("no_attempt", error_type="no_attempt")

        for key_env in key_chain:
            for attempt in range(MAX_RETRIES + 1):
                started = time.perf_counter()
                request_id = str(uuid.uuid4())
                try:
                    if cfg.provider in {"groq", "openai", "cerebras"}:
                        result = self._openai_compat(cfg, messages, key_env=key_env)
                    elif cfg.provider == "anthropic":
                        result = self._anthropic(cfg, messages, key_env=key_env)
                    elif cfg.provider == "gemini":
                        result = self._gemini(cfg, messages, key_env=key_env)
                    elif cfg.provider == "ollama":
                        result = self._ollama(cfg, messages)
                    else:
                        result = self._error_result("unsupported_provider", error_type="unsupported_provider")

                    latency_ms = int((time.perf_counter() - started) * 1000)
                    result["latency_ms"] = latency_ms
                    result["retry_count"] = attempt
                    result["request_id"] = request_id
                    result["prompt_hash"] = prompt_hash

                    self._write_debug_row(cfg, prompt_hash, request_id, result, attempt, latency_ms)

                    if result.get("status") == "ok":
                        return result

                    err_type = str(result.get("error_type") or "")
                    if err_type in {"http_forbidden", "http_unauthorized", "json_decode_error"}:
                        last_result = result
                        break
                    if attempt < MAX_RETRIES and self._retryable(result):
                        time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
                        continue
                    last_result = result
                    break
                except urllib.error.HTTPError as exc:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    body = exc.read().decode("utf-8", errors="replace")[:500]
                    result = self._error_result(
                        f"http_{exc.code}",
                        error_type=self._http_error_type(exc.code),
                        http_status=exc.code,
                        error_message_safe=safe_excerpt(body),
                        raw_text="",
                        latency_ms=latency_ms,
                        retry_count=attempt,
                        request_id=request_id,
                        prompt_hash=prompt_hash,
                    )
                    self._write_debug_row(cfg, prompt_hash, request_id, result, attempt, latency_ms)
                    if attempt < MAX_RETRIES and exc.code in RETRYABLE_HTTP:
                        time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
                        last_result = result
                        continue
                    last_result = result
                    if exc.code in {401, 403}:
                        break
                except TimeoutError:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    result = self._error_result(
                        "timeout",
                        error_type="timeout",
                        latency_ms=latency_ms,
                        retry_count=attempt,
                        request_id=request_id,
                        prompt_hash=prompt_hash,
                    )
                    self._write_debug_row(cfg, prompt_hash, request_id, result, attempt, latency_ms)
                    if attempt < MAX_RETRIES:
                        time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
                        last_result = result
                        continue
                    last_result = result
                except Exception as exc:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    result = self._error_result(
                        str(exc)[:200],
                        error_type="network_error",
                        latency_ms=latency_ms,
                        retry_count=attempt,
                        request_id=request_id,
                        prompt_hash=prompt_hash,
                    )
                    self._write_debug_row(cfg, prompt_hash, request_id, result, attempt, latency_ms)
                    last_result = result
                    break

        return last_result

    def _api_key_chain(self, cfg: Stage4LLMConfig) -> List[str]:
        if cfg.provider == "groq":
            keys = [name for name in GROQ_KEY_ENVS if os.environ.get(name)]
            return keys or ([cfg.api_key_env] if cfg.api_key_env else [])
        return [cfg.api_key_env] if cfg.api_key_env else [""]

    @staticmethod
    def _retryable(result: Dict[str, Any]) -> bool:
        err_type = str(result.get("error_type") or "")
        code = int(result.get("http_status") or 0)
        return err_type in {"timeout", "rate_limit", "server_error", "network_error"} or code in RETRYABLE_HTTP

    @staticmethod
    def _http_error_type(code: int) -> str:
        if code == 429:
            return "rate_limit"
        if code in {401, 403}:
            return "http_forbidden" if code == 403 else "http_unauthorized"
        if code >= 500:
            return "server_error"
        return f"http_{code}"

    @staticmethod
    def _error_result(error: str, *, error_type: str = "", **extra: Any) -> Dict[str, Any]:
        row = {
            "status": "error",
            "error": error,
            "error_type": error_type or error,
            "parsed": {},
            "raw_text": "",
            "raw_content_length": 0,
            "raw_content_empty": True,
            "http_status": extra.get("http_status"),
            "finish_reason": None,
            "response_path_used": "",
        }
        row.update(extra)
        return row

    def _http_post(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
    ) -> Tuple[int, Dict[str, Any]]:
        merged = {**HTTP_HEADERS_BASE, **headers}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=merged,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            status = int(getattr(resp, "status", None) or resp.getcode() or 200)
            body = json.loads(resp.read().decode("utf-8"))
            return status, body

    def _finalize_content(
        self,
        cfg: Stage4LLMConfig,
        *,
        content: str,
        response_path: str,
        finish_reason: Optional[str],
        http_status: int,
    ) -> Dict[str, Any]:
        parsed, ok, parse_error_type = parse_llm_response_text(content)
        raw_len = len(content or "")
        base = {
            "provider": cfg.provider,
            "model": cfg.model,
            "raw_text": content,
            "parsed": parsed if ok else {},
            "raw_content_length": raw_len,
            "raw_content_empty": raw_len == 0,
            "finish_reason": finish_reason,
            "response_path_used": response_path,
            "http_status": http_status,
            "parse_error_type": parse_error_type if not ok else None,
        }
        if raw_len == 0:
            return self._error_result("content_empty", error_type="content_empty", **base)
        if not ok:
            return self._error_result(
                parse_error_type or "json_parse_failed",
                error_type=parse_error_type or "json_parse_failed",
                **base,
            )
        return {"status": "ok", "error": "", "error_type": None, **base}

    def _openai_compat(
        self,
        cfg: Stage4LLMConfig,
        messages: List[Dict[str, str]],
        *,
        key_env: str,
    ) -> Dict[str, Any]:
        key = os.environ.get(key_env, "")
        payload = {
            "model": cfg.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": self.max_tokens,
            "max_completion_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        status, raw = self._http_post(
            cfg.endpoint,
            {"Authorization": f"Bearer {key}"},
            payload,
        )
        content, path, finish = extract_openai_compat_content(raw)
        return self._finalize_content(
            cfg,
            content=content,
            response_path=path,
            finish_reason=finish,
            http_status=status,
        )

    def _anthropic(
        self,
        cfg: Stage4LLMConfig,
        messages: List[Dict[str, str]],
        *,
        key_env: str,
    ) -> Dict[str, Any]:
        system = next((m["content"] for m in messages if m.get("role") == "system"), "")
        user_parts = [m["content"] for m in messages if m.get("role") == "user"]
        payload = {
            "model": cfg.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": "\n".join(user_parts)}],
        }
        status, raw = self._http_post(
            cfg.endpoint,
            {
                "x-api-key": os.environ.get(key_env, ""),
                "anthropic-version": "2023-06-01",
            },
            payload,
        )
        content, path, finish = extract_anthropic_content(raw)
        return self._finalize_content(
            cfg,
            content=content,
            response_path=path,
            finish_reason=finish,
            http_status=status,
        )

    def _gemini(
        self,
        cfg: Stage4LLMConfig,
        messages: List[Dict[str, str]],
        *,
        key_env: str,
    ) -> Dict[str, Any]:
        key = os.environ.get(key_env, "")
        prompt = "\n".join(m["content"] for m in messages)
        url = f"{cfg.endpoint}/{cfg.model}:generateContent?key={key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        status, raw = self._http_post(url, {}, payload)
        content, path, finish = extract_gemini_content(raw)
        return self._finalize_content(
            cfg,
            content=content,
            response_path=path,
            finish_reason=finish,
            http_status=status,
        )

    def _ollama(self, cfg: Stage4LLMConfig, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        url = f"{cfg.endpoint.rstrip('/')}/api/chat"
        payload = {
            "model": cfg.model,
            "messages": messages,
            "stream": False,
            "format": "json",
        }
        status, raw = self._http_post(url, {}, payload)
        content, path, finish = extract_ollama_content(raw)
        return self._finalize_content(
            cfg,
            content=content,
            response_path=path,
            finish_reason=finish,
            http_status=status,
        )

    def _write_debug_row(
        self,
        cfg: Stage4LLMConfig,
        prompt_hash: str,
        request_id: str,
        result: Dict[str, Any],
        retry_count: int,
        latency_ms: int,
    ) -> None:
        raw_text = str(result.get("raw_text") or "")
        append_debug_log(
            {
                "created_at_utc": utc_now_iso(),
                "provider": cfg.provider,
                "model_name": cfg.model,
                "request_id": request_id,
                "prompt_hash": prompt_hash,
                "http_status": result.get("http_status"),
                "success": result.get("status") == "ok",
                "error_type": result.get("error_type"),
                "error_message_safe": safe_excerpt(str(result.get("error") or result.get("error_message_safe") or "")),
                "raw_content_length": result.get("raw_content_length", len(raw_text)),
                "raw_content_empty": bool(result.get("raw_content_empty", not raw_text)),
                "raw_content_excerpt": safe_excerpt(raw_text),
                "finish_reason": result.get("finish_reason"),
                "latency_ms": latency_ms,
                "retry_count": retry_count,
                "response_path_used": result.get("response_path_used") or "",
            }
        )
