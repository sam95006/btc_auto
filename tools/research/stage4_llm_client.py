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
from tools.research.stage4_rate_limit_gate import Stage4LLMRateGate
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
    "openai": os.environ.get("STAGE4_OPENAI_LLM_MODEL", "gpt-4o-mini"),
    "anthropic": os.environ.get("STAGE4_ANTHROPIC_LLM_MODEL", "claude-3-5-haiku-20241022"),
    "gemini": os.environ.get("STAGE4_GEMINI_LLM_MODEL", "gemini-2.0-flash"),
    "ollama": os.environ.get("STAGE4_OLLAMA_LLM_MODEL", "llama3.3"),
    "cerebras": os.environ.get(
        "STAGE4_CEREBRAS_LLM_MODEL",
        os.environ.get("STAGE4_SECONDARY_LLM_MODEL", "gpt-oss-120b"),
    ),
}

GROQ_KEY_ENVS = ("GROQ_API_KEY_PRIMARY", "GROQ_API_KEY_SECONDARY", "GROQ_API_KEY")


def _first_env_key(names: Tuple[str, ...]) -> str:
    for name in names:
        if os.environ.get(name):
            return name
    return ""

RETRYABLE_HTTP = frozenset({408, 500, 502, 503, 504})
MAX_RETRIES = 1
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


class ProviderRateLimited(Exception):
    """LLM provider returned 429 or local rate gate blocked the call."""

    def __init__(
        self,
        *,
        provider: str,
        model_name: str,
        symbol: str = "",
        retry_count: int = 0,
        reason: str = "provider_rate_limited",
        event_type: str = "",
        call_kind: str = "decision",
        gate_status: Dict[str, Any] | None = None,
        http_status: int | None = None,
        provider_attempts: List[Dict[str, Any]] | None = None,
        fallback_used: bool = False,
        fallback_reason: str = "",
    ) -> None:
        self.provider = provider
        self.model_name = model_name
        self.symbol = symbol
        self.retry_count = retry_count
        self.reason = reason
        self.event_type = event_type or _reason_to_event_type(reason)
        self.call_kind = call_kind
        self.gate_status = gate_status or {}
        self.http_status = http_status
        self.provider_attempts = list(provider_attempts or [])
        self.fallback_used = fallback_used
        self.fallback_reason = fallback_reason
        super().__init__(reason)


def _reason_to_event_type(reason: str) -> str:
    mapping = {
        "rate_limit": "provider_http_429",
        "rate_limit_gate": "local_rate_gate_skip",
        "backoff_active_skip": "backoff_active_skip",
        "local_rate_gate_skip": "local_rate_gate_skip",
        "empty_llm_response": "provider_quota_exhausted",
        "provider_chain_failed": "provider_chain_failed",
    }
    return mapping.get(reason, "provider_rate_limited")


class RealLLMRequiredError(RuntimeError):
    """Raised when real LLM is required but unavailable (no mock fallback)."""

    def __init__(self, reason: str = "missing_real_llm_key") -> None:
        self.reason = reason
        super().__init__(reason)


def groq_max_tokens() -> int:
    raw = os.environ.get("NEXUS_LLM_MAX_COMPLETION_TOKENS", "450").strip()
    try:
        return max(128, int(float(raw)))
    except (TypeError, ValueError):
        return 450


def cerebras_max_tokens() -> int:
    from tools.research.stage4_cerebras_payload import resolve_cerebras_max_tokens

    return resolve_cerebras_max_tokens()


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
    from tools.research.stage4_groq_key_registry import GroqKeyRegistry
    from tools.research.stage4_provider_chain import dedupe_groq_api_keys

    _bridge_groq_env_aliases()
    dedup = dedupe_groq_api_keys()
    used = _first_env_key(GROQ_KEY_ENVS)
    present_names = [name for name in GROQ_KEY_ENVS if os.environ.get(name)]
    health = GroqKeyRegistry.shared().health_report()
    return {
        "groq_key_aliases_checked": list(GROQ_KEY_ENVS),
        "groq_key_present": bool(present_names),
        "groq_key_env_used": used or None,
        "groq_key_env_count": len(present_names),
        "provider_chain_deduped": dedup.get("provider_chain_deduped"),
        "deduped_provider_key_count": dedup.get("deduped_provider_key_count"),
        "groq_key_fingerprints": dedup.get("groq_key_fingerprints"),
        **health,
    }


def real_llm_preflight(*, use_real_llm: bool, provider: str = "", model: str = "") -> Tuple[bool, str]:
    if not use_real_llm:
        return True, ""
    if mock_fallback_allowed(use_real_llm=True):
        return True, ""
    from tools.research.stage4_provider_chain import Stage4ProviderChainClient, provider_key_configured, resolve_provider_chain

    chain = resolve_provider_chain()
    if not any(provider_key_configured(p) for p in chain):
        return False, "missing_real_llm_key"
    client = Stage4ProviderChainClient(load_env=True)
    avail = client.availability()
    if avail.get("real_llm_available"):
        return True, ""
    return False, str(avail.get("reason") or "missing_real_llm_key")


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
        self.groq_max_tokens = groq_max_tokens()
        self.cerebras_max_tokens = cerebras_max_tokens()
        self.max_tokens = self.groq_max_tokens
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
        symbol: str = "",
        use_rate_gate: bool = True,
        call_kind: str = "decision",
    ) -> Dict[str, Any]:
        if not self.available or not self.config:
            return self._error_result("llm_unavailable", error_type="llm_unavailable")

        cfg = self.config
        from tools.research.stage4_provider_chain import Stage4ProviderCircuitBreaker

        circuit = Stage4ProviderCircuitBreaker.shared()
        if circuit.is_open(cfg.provider):
            return self._error_result(
                "provider_circuit_breaker_open",
                error_type="provider_circuit_breaker_open",
                provider=cfg.provider,
                model=cfg.model,
                symbol=symbol,
                call_kind=call_kind,
            )

        gate = Stage4LLMRateGate.shared()
        if use_rate_gate:
            block = gate.block_reason()
            if block:
                status = gate.status_dict()
                return self._error_result(
                    "rate_limit_gate_blocked",
                    error_type=block,
                    provider=cfg.provider,
                    model=cfg.model,
                    symbol=symbol,
                    call_kind=call_kind,
                    **status,
                )

        if use_rate_gate:
            gate.record_call_start()

        key_chain = self._api_key_chain(cfg)
        last_result: Dict[str, Any] = self._error_result("no_attempt", error_type="no_attempt")
        prefer_chain_fallback: Dict[str, Any] | None = None

        for key_env in key_chain:
            key_val = (os.environ.get(key_env) or "").strip() if key_env else ""
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
                    result["call_kind"] = call_kind

                    self._write_debug_row(cfg, prompt_hash, request_id, result, attempt, latency_ms)

                    if result.get("status") == "ok":
                        if cfg.provider == "groq" and key_val:
                            self._record_groq_key_outcome(env_name=key_env, key_value=key_val, result=result)
                        if use_rate_gate:
                            gate.record_success()
                        return result

                    if cfg.provider == "groq" and key_val:
                        self._record_groq_key_outcome(env_name=key_env, key_value=key_val, result=result)

                    if self.is_chain_fallback_eligible(result):
                        prefer_chain_fallback = result

                    err_type = str(result.get("error_type") or "")
                    if err_type == "rate_limit":
                        circuit.trip(cfg.provider)
                        if use_rate_gate:
                            gate.record_rate_limit()
                        last_result = result
                        break
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
                    err_type = self._http_error_type(exc.code)
                    result = self._error_result(
                        f"http_{exc.code}",
                        error_type=err_type,
                        http_status=exc.code,
                        error_message_safe=safe_excerpt(body),
                        raw_text="",
                        latency_ms=latency_ms,
                        retry_count=attempt,
                        request_id=request_id,
                        prompt_hash=prompt_hash,
                    )
                    self._write_debug_row(cfg, prompt_hash, request_id, result, attempt, latency_ms)
                    if self.is_chain_fallback_eligible(result):
                        prefer_chain_fallback = result
                    if exc.code == 429:
                        circuit.trip(cfg.provider)
                        if use_rate_gate:
                            gate.record_rate_limit()
                        last_result = result
                        break
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

        # One-shot Cerebras parse retry with boosted max_tokens (stability only).
        if (
            cfg.provider == "cerebras"
            and env_truthy("STAGE4_CEREBRAS_PARSE_RETRY_ONCE", True)
            and last_result.get("status") != "ok"
            and not last_result.get("cerebras_parse_retry")
        ):
            err_type = str(last_result.get("error_type") or "")
            if err_type in {
                "provider_response_truncated",
                "json_decode_error",
                "provider_invalid_json",
            }:
                from tools.research.stage4_cerebras_payload import (
                    cerebras_retry_token_boost,
                    resolve_cerebras_max_tokens,
                )

                boosted = min(2048, resolve_cerebras_max_tokens() + cerebras_retry_token_boost())
                key_env = key_chain[0] if key_chain else (cfg.api_key_env or "")
                retry = self._openai_compat(
                    cfg,
                    messages,
                    key_env=key_env,
                    max_tokens_override=boosted,
                )
                retry["cerebras_parse_retry"] = True
                retry["max_tokens_used"] = boosted
                if retry.get("status") == "ok":
                    if use_rate_gate:
                        gate.record_success()
                    return retry
                last_result = retry

        if prefer_chain_fallback is not None and last_result.get("status") != "ok":
            return prefer_chain_fallback
        return last_result

    def _api_key_chain(self, cfg: Stage4LLMConfig) -> List[str]:
        if cfg.provider == "groq":
            from tools.research.stage4_provider_chain import deduped_groq_key_envs

            keys = deduped_groq_key_envs(skip_disabled=True)
            return keys or ([cfg.api_key_env] if cfg.api_key_env else [])
        return [cfg.api_key_env] if cfg.api_key_env else [""]

    @staticmethod
    def _record_groq_key_outcome(*, env_name: str, key_value: str, result: Dict[str, Any]) -> None:
        from tools.research.stage4_groq_key_registry import GroqKeyRegistry

        registry = GroqKeyRegistry.shared()
        if result.get("status") == "ok":
            registry.record_success(env_name=env_name, key_value=key_value)
            return
        registry.record_error(
            env_name=env_name,
            key_value=key_value,
            error_type=str(result.get("error_type") or ""),
            http_status=int(result.get("http_status") or 0) or None,
        )

    @staticmethod
    def _retryable(result: Dict[str, Any]) -> bool:
        err_type = str(result.get("error_type") or "")
        code = int(result.get("http_status") or 0)
        if err_type == "rate_limit" or code == 429:
            return False
        return err_type in {"timeout", "server_error", "network_error"} or code in RETRYABLE_HTTP

    @staticmethod
    def is_rate_limited_result(result: Dict[str, Any]) -> bool:
        err_type = str(result.get("error_type") or "")
        code = int(result.get("http_status") or 0)
        gate_types = {
            "rate_limit",
            "rate_limit_gate",
            "local_rate_gate_skip",
            "backoff_active_skip",
            "provider_circuit_breaker_open",
        }
        return err_type in gate_types or code == 429

    @staticmethod
    def is_quota_exhaustion_result(result: Dict[str, Any]) -> bool:
        """Empty provider response treated as quota exhaustion (eligible for secondary fallback)."""
        err_type = str(result.get("error_type") or "")
        if err_type in {"provider_quota_exhausted", "empty_llm_response"}:
            return True
        if err_type in {"provider_empty_response", "provider_response_truncated", "json_decode_error"}:
            return False
        if err_type == "content_empty" and bool(result.get("raw_content_empty")):
            return not bool(str(result.get("raw_text") or "").strip())
        return False

    @staticmethod
    def is_chain_fallback_eligible(result: Dict[str, Any]) -> bool:
        """Primary provider failures that should try the next real LLM in chain."""
        if Stage4LLMClient.is_rate_limited_result(result):
            return True
        if Stage4LLMClient.is_quota_exhaustion_result(result):
            return True
        return False

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
        if cfg.provider == "cerebras":
            return self._finalize_cerebras_content(
                cfg,
                content=content,
                response_path=response_path,
                finish_reason=finish_reason,
                http_status=http_status,
            )
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

    def _finalize_cerebras_content(
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
        finish = str(finish_reason or "").lower()
        base: Dict[str, Any] = {
            "provider": "cerebras",
            "model": cfg.model,
            "raw_text": content,
            "parsed": parsed if ok else {},
            "raw_content_length": raw_len,
            "response_text_chars": raw_len,
            "raw_content_empty": raw_len == 0,
            "finish_reason": finish_reason,
            "response_path_used": response_path,
            "http_status": http_status,
            "parse_error_type": parse_error_type if not ok else None,
        }
        if raw_len == 0 and http_status == 200:
            return self._error_result(
                "provider_empty_response",
                error_type="provider_empty_response",
                empty_response=True,
                **base,
            )
        if not ok:
            if finish == "length":
                return self._error_result(
                    "provider_response_truncated",
                    error_type="provider_response_truncated",
                    json_decode_error=True,
                    **base,
                )
            return self._error_result(
                parse_error_type or "provider_invalid_json",
                error_type=parse_error_type or "provider_invalid_json",
                json_decode_error=True,
                **base,
            )
        return {"status": "ok", "error": "", "error_type": None, **base}

    def _openai_compat(
        self,
        cfg: Stage4LLMConfig,
        messages: List[Dict[str, str]],
        *,
        key_env: str,
        max_tokens_override: int | None = None,
    ) -> Dict[str, Any]:
        from tools.research.stage4_groq_payload import (
            build_stage4_groq_openai_payload,
            groq_payload_metadata,
            parse_groq_error_safe,
        )

        key = os.environ.get(key_env, "")
        if cfg.provider == "groq":
            payload = build_stage4_groq_openai_payload(
                model=cfg.model,
                messages=messages,
                max_tokens=self.groq_max_tokens,
                temperature=0.2,
            )
        elif cfg.provider == "cerebras":
            from tools.research.stage4_cerebras_payload import (
                build_stage4_cerebras_openai_payload,
                cerebras_payload_metadata,
            )

            cerebras_tokens = max_tokens_override if max_tokens_override is not None else self.cerebras_max_tokens
            payload = build_stage4_cerebras_openai_payload(
                model=cfg.model,
                messages=messages,
                max_tokens=cerebras_tokens,
                temperature=0.2,
            )
        else:
            payload = {
                "model": cfg.model,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": self.max_tokens,
                "max_completion_tokens": self.max_tokens,
                "response_format": {"type": "json_object"},
            }
        try:
            status, raw = self._http_post(
                cfg.endpoint,
                {"Authorization": f"Bearer {key}"},
                payload,
            )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            err_safe = parse_groq_error_safe(body)
            if cfg.provider == "cerebras":
                from tools.research.stage4_cerebras_payload import classify_cerebras_http_error

                err_type = classify_cerebras_http_error(http_status=int(exc.code or 0), body=body)
            else:
                err_type = err_safe.get("error_type") or self._http_error_type(int(exc.code or 0))
            return self._error_result(
                err_safe.get("error_message_safe") or f"http_{exc.code}",
                error_type=err_type,
                http_status=int(exc.code or 0),
                error_message_safe=err_safe.get("error_message_safe"),
                request_id=err_safe.get("request_id"),
                provider=cfg.provider,
                **groq_payload_metadata(model=cfg.model) if cfg.provider == "groq" else {},
            )
        content, path, finish = extract_openai_compat_content(raw)
        result = self._finalize_content(
            cfg,
            content=content,
            response_path=path,
            finish_reason=finish,
            http_status=status,
        )
        if cfg.provider == "groq":
            result.update(groq_payload_metadata(model=cfg.model))
        elif cfg.provider == "cerebras":
            from tools.research.stage4_cerebras_payload import cerebras_payload_metadata

            result.update(cerebras_payload_metadata(model=cfg.model))
        return result

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
                "response_text_chars": result.get("response_text_chars", result.get("raw_content_length", len(raw_text))),
                "raw_content_empty": bool(result.get("raw_content_empty", not raw_text)),
                "empty_response": bool(result.get("empty_response")),
                "json_decode_error": bool(result.get("json_decode_error")),
                "raw_content_excerpt": safe_excerpt(raw_text),
                "finish_reason": result.get("finish_reason"),
                "latency_ms": latency_ms,
                "retry_count": retry_count,
                "response_path_used": result.get("response_path_used") or "",
                "call_kind": result.get("call_kind") or "decision",
            }
        )
