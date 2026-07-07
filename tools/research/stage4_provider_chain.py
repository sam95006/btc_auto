"""Stage 4 multi-provider LLM chain with Groq dedup and circuit breaker."""
from __future__ import annotations

import hashlib
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from tools.research.stage4_llm_client import (
    DEFAULT_MODELS,
    GROQ_KEY_ENVS,
    ProviderRateLimited,
    RealLLMRequiredError,
    Stage4LLMClient,
    _bridge_groq_env_aliases,
    env_truthy,
    mock_fallback_allowed,
)
from tools.research.stage4_provider_quota_governor import Stage4ProviderQuotaGovernor

ALLOWED_REAL_PROVIDERS = frozenset({"groq", "cerebras", "openai", "anthropic", "gemini", "ollama"})

FALLBACK_REASON_MAP = {
    "rate_limit": "groq_rate_limited",
    "provider_http_429": "groq_rate_limited",
    "provider_rate_limited": "groq_rate_limited",
    "provider_quota_exhausted": "groq_provider_quota_exhausted",
    "provider_circuit_breaker_open": "groq_rate_limited",
    "content_empty": "groq_provider_quota_exhausted",
    "empty_llm_response": "groq_provider_quota_exhausted",
}


def key_fingerprint(key: str) -> str:
    if not key:
        return ""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def dedupe_groq_api_keys() -> Dict[str, Any]:
    """Remove duplicate Groq keys (same value across PRIMARY/SECONDARY/legacy)."""
    _bridge_groq_env_aliases()
    seen_values: Dict[str, str] = {}
    deduped_envs: List[str] = []
    fingerprints: List[str] = []
    raw_count = 0
    for name in GROQ_KEY_ENVS:
        val = (os.environ.get(name) or "").strip()
        if not val:
            continue
        raw_count += 1
        fp = key_fingerprint(val)
        if val in seen_values:
            continue
        seen_values[val] = name
        deduped_envs.append(name)
        fingerprints.append(fp)
    return {
        "provider_chain_deduped": raw_count > len(deduped_envs),
        "deduped_provider_key_count": len(deduped_envs),
        "groq_key_env_count_raw": raw_count,
        "groq_key_env_count_deduped": len(deduped_envs),
        "groq_key_fingerprints": fingerprints,
        "groq_key_envs_deduped": deduped_envs,
    }


def deduped_groq_key_envs(*, skip_disabled: bool = True) -> List[str]:
    status = dedupe_groq_api_keys()
    envs = list(status.get("groq_key_envs_deduped") or [])
    if not envs:
        envs = [name for name in GROQ_KEY_ENVS if os.environ.get(name)]
    if not skip_disabled:
        return envs
    try:
        from tools.research.stage4_groq_key_registry import GroqKeyRegistry

        registry = GroqKeyRegistry.shared()
        filtered: List[str] = []
        for env_name in envs:
            val = (os.environ.get(env_name) or "").strip()
            if val and not registry.is_disabled(val):
                filtered.append(env_name)
        return filtered
    except Exception:
        return envs


def resolve_provider_chain() -> List[str]:
    chain_raw = (os.environ.get("STAGE4_LLM_PROVIDER_CHAIN") or "").strip()
    if chain_raw:
        parts = [p.strip().lower() for p in chain_raw.split(",") if p.strip()]
        return [p for p in parts if p in ALLOWED_REAL_PROVIDERS]
    primary = (os.environ.get("STAGE4_PRIMARY_LLM_PROVIDER") or os.environ.get("STAGE4_LLM_PROVIDER") or "groq").strip().lower()
    secondary = (os.environ.get("STAGE4_SECONDARY_LLM_PROVIDER") or "").strip().lower()
    chain: List[str] = []
    if primary:
        chain.append(primary)
    if secondary and secondary not in chain:
        chain.append(secondary)
    return chain or ["groq"]


def secondary_fallback_allowed() -> bool:
    return env_truthy("STAGE4_ALLOW_SECONDARY_REAL_LLM_FALLBACK", False)


def provider_key_env(provider: str) -> str:
    mapping = {
        "groq": "GROQ_API_KEY_PRIMARY",
        "cerebras": "CEREBRAS_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GOOGLE_API_KEY",
    }
    if provider == "groq":
        envs = deduped_groq_key_envs()
        return envs[0] if envs else ""
    return mapping.get(provider, "")


def provider_key_configured(provider: str) -> bool:
    if provider == "groq":
        return bool(deduped_groq_key_envs())
    if provider == "ollama":
        return bool(os.environ.get("OLLAMA_BASE_URL", "").strip())
    env_name = provider_key_env(provider)
    return bool(env_name and os.environ.get(env_name))


def model_for_provider(provider: str, *, is_primary: bool = True) -> str:
    if is_primary:
        explicit = (os.environ.get("STAGE4_LLM_MODEL") or "").strip()
        if explicit and provider == resolve_provider_chain()[0]:
            return explicit
    secondary_model = (os.environ.get("STAGE4_SECONDARY_LLM_MODEL") or "").strip()
    if not is_primary and secondary_model:
        return secondary_model
    per_provider = (os.environ.get(f"STAGE4_{provider.upper()}_LLM_MODEL") or "").strip()
    if per_provider:
        return per_provider
    return DEFAULT_MODELS.get(provider, "")


class Stage4ProviderCircuitBreaker:
    """Per-provider circuit breaker after HTTP 429."""

    _shared: Optional["Stage4ProviderCircuitBreaker"] = None

    def __init__(self) -> None:
        self._open_until: Dict[str, float] = {}
        self._triggered_count = 0

    @classmethod
    def shared(cls) -> "Stage4ProviderCircuitBreaker":
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    @classmethod
    def reset_shared(cls) -> None:
        cls._shared = None

    @staticmethod
    def cooldown_seconds() -> float:
        raw = os.environ.get("STAGE4_PROVIDER_CIRCUIT_BREAKER_SECONDS", "300")
        try:
            return max(30.0, float(raw))
        except (TypeError, ValueError):
            return 300.0

    def is_open(self, provider: str) -> bool:
        until = self._open_until.get(provider, 0.0)
        return time.monotonic() < until

    def trip(self, provider: str, *, seconds: float | None = None) -> None:
        cooldown = seconds if seconds is not None else self.cooldown_seconds()
        self._open_until[provider] = time.monotonic() + cooldown
        self._triggered_count += 1

    @property
    def triggered_count(self) -> int:
        return self._triggered_count


class Stage4ProviderChainClient:
    """Try providers in chain; fallback to secondary real LLM on primary rate limit."""

    def __init__(self, *, load_env: bool = True) -> None:
        if load_env:
            from tools.research.stage4_llm_client import _load_local_env

            _load_local_env()
        self.dedup_status = dedupe_groq_api_keys()
        self.provider_chain = resolve_provider_chain()
        self.circuit_breaker = Stage4ProviderCircuitBreaker.shared()
        self._clients: Dict[str, Stage4LLMClient] = {}
        self.primary_provider = self.provider_chain[0] if self.provider_chain else "groq"
        self.secondary_provider = self.provider_chain[1] if len(self.provider_chain) > 1 else ""
        self.secondary_available = bool(self.secondary_provider and provider_key_configured(self.secondary_provider))
        self.fallback_allowed = secondary_fallback_allowed()
        self._last_attempts: List[Dict[str, Any]] = []

    def _client_for(self, provider: str, *, is_primary: bool) -> Stage4LLMClient:
        if provider not in self._clients:
            self._clients[provider] = Stage4LLMClient(
                provider=provider,
                model=model_for_provider(provider, is_primary=is_primary),
                load_env=False,
            )
        return self._clients[provider]

    def chain_status(self) -> Dict[str, Any]:
        governor = Stage4ProviderQuotaGovernor.shared()
        return {
            "provider_chain": self.provider_chain,
            "primary_provider": self.primary_provider,
            "secondary_provider": self.secondary_provider or None,
            "secondary_provider_available": self.secondary_available,
            "fallback_allowed": self.fallback_allowed,
            **self.dedup_status,
            "provider_circuit_breaker_triggered_count": self.circuit_breaker.triggered_count,
            **governor.summary_fields(),
        }

    def availability(self) -> Dict[str, Any]:
        for idx, prov in enumerate(self.provider_chain):
            if not provider_key_configured(prov):
                continue
            client = self._client_for(prov, is_primary=(idx == 0))
            avail = client.availability()
            if avail.get("real_llm_available"):
                return {
                    **avail,
                    "provider_chain": self.provider_chain,
                    "secondary_provider_available": self.secondary_available,
                }
        return {
            "real_llm_available": False,
            "real_llm_unavailable": True,
            "provider": None,
            "model_name": None,
            "reason": "no_allowed_provider_configured",
            "provider_chain": self.provider_chain,
            "secondary_provider_available": self.secondary_available,
        }

    @staticmethod
    def _is_fallback_eligible(result: Dict[str, Any]) -> bool:
        return Stage4LLMClient.is_chain_fallback_eligible(result)

    @staticmethod
    def _normalize_primary_error(err_type: str, result: Dict[str, Any]) -> str:
        if err_type in {"content_empty", "empty_llm_response"} and Stage4LLMClient.is_quota_exhaustion_result(result):
            return "provider_quota_exhausted"
        if err_type == "provider_empty_response":
            return "provider_empty_response"
        return err_type or "provider_error"

    @staticmethod
    def _attempt_result(provider: str, result: Dict[str, Any]) -> Dict[str, Any]:
        err_type = str(result.get("error_type") or "")
        if result.get("status") == "ok":
            return {"provider": provider, "result": "success"}
        if err_type == "provider_circuit_breaker_open":
            return {"provider": provider, "result": "failed", "error_type": err_type}
        if Stage4LLMClient.is_chain_fallback_eligible(result):
            normalized = Stage4ProviderChainClient._normalize_primary_error(err_type, result)
            return {
                "provider": provider,
                "result": "failed",
                "error_type": normalized,
                "http_status": result.get("http_status"),
            }
        return {
            "provider": provider,
            "result": "failed",
            "error_type": err_type or "provider_error",
            "http_status": result.get("http_status"),
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
        attempts: List[Dict[str, Any]] = []
        last_result: Dict[str, Any] = {}
        primary_provider = self.primary_provider
        primary_error = ""
        fallback_used = False
        fallback_reason = ""
        governor = Stage4ProviderQuotaGovernor.shared()

        for idx, provider in enumerate(self.provider_chain):
            is_primary = idx == 0
            if not provider_key_configured(provider):
                attempts.append({"provider": provider, "result": "skipped", "error_type": "missing_api_key"})
                continue
            if provider == "groq" and governor.should_skip_groq():
                governor.record_cooldown_skip()
                attempts.append(
                    {
                        "provider": "groq",
                        "result": "skipped",
                        "error_type": "groq_tpm_cooldown",
                    }
                )
                if is_primary:
                    primary_error = "rate_limit"
                if self.fallback_allowed and idx + 1 < len(self.provider_chain):
                    continue
                break
            if self.circuit_breaker.is_open(provider):
                attempts.append(
                    {
                        "provider": provider,
                        "result": "circuit_breaker_open",
                        "error_type": "provider_circuit_breaker_open",
                    }
                )
                if is_primary:
                    primary_error = "provider_circuit_breaker_open"
                continue

            client = self._client_for(provider, is_primary=is_primary)
            from tools.research.stage4_prompt_builder import inject_provider_strict_prompt

            provider_messages = inject_provider_strict_prompt(messages, provider)
            result = client.complete_json(
                provider_messages,
                prompt_hash=prompt_hash,
                symbol=symbol,
                use_rate_gate=use_rate_gate and is_primary,
                call_kind=call_kind,
            )
            attempts.append(self._attempt_result(provider, result))
            last_result = result

            if result.get("status") == "ok":
                if not is_primary:
                    fallback_used = True
                    fallback_reason = FALLBACK_REASON_MAP.get(primary_error, "groq_rate_limited")
                enriched = dict(result)
                enriched.update(
                    {
                        "provider": provider,
                        "model": result.get("model") or client.config.model if client.config else "",
                        "provider_chain": self.provider_chain,
                        "provider_attempts": attempts,
                        "fallback_used": fallback_used,
                        "fallback_reason": fallback_reason if fallback_used else None,
                        "primary_provider": primary_provider,
                        "primary_error": primary_error if fallback_used else None,
                        "is_mock_ai": False,
                    }
                )
                self._last_attempts = attempts
                return enriched

            err_type = str(result.get("error_type") or "")
            if provider == "groq" and (
                err_type in {"rate_limit", "provider_http_429", "provider_rate_limited"}
                or int(result.get("http_status") or 0) == 429
            ):
                governor.record_groq_429(error_type=err_type, http_status=int(result.get("http_status") or 0) or None)
            if is_primary:
                primary_error = self._normalize_primary_error(err_type, result) if self._is_fallback_eligible(result) else (
                    err_type or "provider_error"
                )

            if self._is_fallback_eligible(result):
                if idx + 1 < len(self.provider_chain) and self.fallback_allowed:
                    continue
                break

            if err_type in {"http_forbidden", "http_unauthorized"}:
                if is_primary and idx + 1 < len(self.provider_chain) and self.fallback_allowed:
                    primary_error = err_type or "http_unauthorized"
                    continue
                break

        self._last_attempts = attempts
        if last_result:
            last_result = dict(last_result)
            last_result["provider_attempts"] = attempts
            last_result["provider_chain"] = self.provider_chain
            last_result["fallback_used"] = False
            last_result["primary_provider"] = primary_provider
            last_result["primary_error"] = primary_error or last_result.get("error_type")
            if last_result.get("status") != "ok" and len(attempts) > 1:
                last_result["error_type"] = "provider_chain_failed"
                last_result["status"] = "error"
        return last_result

    def last_provider_attempts(self) -> List[Dict[str, Any]]:
        return list(self._last_attempts)


def assert_real_llm_chain_available(*, use_real_llm: bool) -> Tuple[bool, str]:
    if not use_real_llm:
        return True, ""
    if mock_fallback_allowed(use_real_llm=True):
        return True, ""
    client = Stage4ProviderChainClient(load_env=True)
    avail = client.availability()
    if avail.get("real_llm_available"):
        return True, ""
    return False, str(avail.get("reason") or "missing_real_llm_key")
