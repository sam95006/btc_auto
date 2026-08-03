"""Provider-neutral AI gateway — schema-validated, fail-closed, redacted."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

ALLOWED_RESULT_STATUS = frozenset(
    {
        "SUCCESS",
        "INVALID_SCHEMA",
        "TIMEOUT",
        "RATE_LIMITED",
        "PROVIDER_UNAVAILABLE",
        "MODEL_UNAVAILABLE",
        "SAFETY_BLOCK",
        "UNKNOWN",
    }
)

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|password|token|authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)BYBIT[_A-Z0-9]*\s*[:=]\s*\S+"),
    re.compile(r"(?i)NEXUS_[A-Z0-9_]*KEY\s*[:=]\s*\S+"),
    re.compile(r"(?i)GROQ_API_KEY[_A-Z]*\s*[:=]\s*\S+"),
    re.compile(r"(?i)CEREBRAS_API_KEY\s*[:=]\s*\S+"),
    re.compile(r"(?i)SAMBANOVA_API_KEY\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bgsk_[A-Za-z0-9]{8,}\b"),
    re.compile(r"(?i)\bcsk_[A-Za-z0-9]{8,}\b"),
]


def redact_for_external(text: str) -> str:
    out = text
    for pat in SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    # Mask long hex-like secrets
    out = re.sub(r"\b[0-9a-fA-F]{32,}\b", "[REDACTED_HEX]", out)
    return out


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@dataclass
class ProviderRequestRecord:
    provider_id: str
    model_id: str
    model_version_or_fingerprint: str
    role: str
    request_id: str
    prompt_schema_version: str
    prompt_hash: str
    input_hash: str
    output_hash: str | None
    started_at: str
    completed_at: str | None
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    retry_count: int
    rate_limit_state: str
    result_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AIProvider(Protocol):
    provider_id: str

    def complete_json(
        self,
        *,
        model_id: str,
        prompt: str,
        schema: dict[str, Any],
        timeout_s: float = 30.0,
    ) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
        """Returns (parsed_or_none, result_status, meta)."""
        ...


@dataclass
class MockProvider:
    provider_id: str
    responses: dict[str, Any] = field(default_factory=dict)
    force_status: str | None = None
    available: bool = True

    def complete_json(
        self,
        *,
        model_id: str,
        prompt: str,
        schema: dict[str, Any],
        timeout_s: float = 30.0,
    ) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
        if not self.available:
            return None, "PROVIDER_UNAVAILABLE", {"model_id": model_id}
        if self.force_status:
            return None, self.force_status, {"model_id": model_id}
        key = str(schema.get("title") or "default")
        payload = self.responses.get(key) or self.responses.get("default") or {"ok": True}
        return payload, "SUCCESS", {"model_id": model_id, "input_tokens": 10, "output_tokens": 10}


def validate_against_schema(obj: Any, schema: dict[str, Any]) -> bool:
    """Minimal strict JSON object schema check (required keys + types)."""
    if not isinstance(obj, dict):
        return False
    required = schema.get("required") or []
    props = schema.get("properties") or {}
    for key in required:
        if key not in obj:
            return False
    for key, val in obj.items():
        if key not in props:
            return False
        expected = props[key].get("type")
        if expected == "string" and not isinstance(val, str):
            return False
        if expected == "number" and not isinstance(val, (int, float)):
            return False
        if expected == "integer" and not isinstance(val, int):
            return False
        if expected == "boolean" and not isinstance(val, bool):
            return False
        if expected == "array" and not isinstance(val, list):
            return False
        if expected == "object" and not isinstance(val, dict):
            return False
    return True


@dataclass
class AIGateway:
    providers: dict[str, AIProvider]
    role_map: dict[str, str] = field(default_factory=dict)
    records: list[ProviderRequestRecord] = field(default_factory=list)

    @classmethod
    def from_env(cls, *, mock_for_ci: bool = False) -> "AIGateway":
        if mock_for_ci or os.getenv("NEXUS_AI_MOCK", "1") == "1":
            providers: dict[str, AIProvider] = {
                "OLLAMA": MockProvider("OLLAMA"),
                "GROQ": MockProvider("GROQ"),
                "GEMINI": MockProvider("GEMINI"),
                "CLOUDFLARE_WORKERS_AI": MockProvider("CLOUDFLARE_WORKERS_AI"),
                "OPENROUTER": MockProvider("OPENROUTER"),
            }
        else:
            # Real adapters are env-driven stubs that report unavailable without keys.
            providers = {
                "OLLAMA": EnvHttpProvider("OLLAMA", os.getenv("NEXUS_OLLAMA_BASE_URL", "")),
                "GROQ": EnvHttpProvider("GROQ", os.getenv("NEXUS_GROQ_API_KEY", "")),
                "GEMINI": EnvHttpProvider("GEMINI", os.getenv("NEXUS_GEMINI_API_KEY", "")),
                "CLOUDFLARE_WORKERS_AI": EnvHttpProvider(
                    "CLOUDFLARE_WORKERS_AI", os.getenv("NEXUS_CF_AI_TOKEN", "")
                ),
                "OPENROUTER": EnvHttpProvider("OPENROUTER", os.getenv("NEXUS_OPENROUTER_API_KEY", "")),
            }
        role_map = {
            "lesson_normalizer": os.getenv("NEXUS_AI_ROLE_LESSON_NORMALIZER", "OLLAMA"),
            "bulk_research_summarizer": os.getenv("NEXUS_AI_ROLE_BULK_SUMMARIZER", "OLLAMA"),
            "main_market_reasoner": os.getenv("NEXUS_AI_ROLE_MAIN_REASONER", "GROQ"),
            "reflection_reasoner": os.getenv("NEXUS_AI_ROLE_REFLECTION", "GEMINI"),
            "independent_reflection_critic": os.getenv(
                "NEXUS_AI_ROLE_REFLECTION_CRITIC", "GROQ"
            ),
            "embedding_provider": os.getenv("NEXUS_AI_ROLE_EMBEDDING", "OLLAMA"),
        }
        return cls(providers=providers, role_map=role_map)

    def invoke_role(
        self,
        *,
        role: str,
        model_id: str,
        prompt: str,
        schema: dict[str, Any],
        prompt_schema_version: str,
        allow_silent_failover: bool = False,
    ) -> tuple[dict[str, Any] | None, ProviderRequestRecord, str]:
        """Returns (validated_json_or_none, record, order_permission)."""
        if allow_silent_failover:
            raise ValueError("silent_failover_forbidden")
        provider_id = self.role_map.get(role)
        started = datetime.now(timezone.utc)
        request_id = str(uuid.uuid4())
        redacted = redact_for_external(prompt)
        prompt_hash = _sha(prompt_schema_version + "|" + json.dumps(schema, sort_keys=True))
        input_hash = _sha(redacted)

        if not provider_id or provider_id not in self.providers:
            rec = ProviderRequestRecord(
                provider_id=provider_id or "NONE",
                model_id=model_id,
                model_version_or_fingerprint="unknown",
                role=role,
                request_id=request_id,
                prompt_schema_version=prompt_schema_version,
                prompt_hash=prompt_hash,
                input_hash=input_hash,
                output_hash=None,
                started_at=started.strftime("%Y-%m-%dT%H:%M:%SZ"),
                completed_at=started.strftime("%Y-%m-%dT%H:%M:%SZ"),
                latency_ms=0,
                input_tokens=None,
                output_tokens=None,
                retry_count=0,
                rate_limit_state="n/a",
                result_status="PROVIDER_UNAVAILABLE",
            )
            self.records.append(rec)
            return None, rec, "BLOCK"

        provider = self.providers[provider_id]
        t0 = time.perf_counter()
        try:
            parsed, status, meta = provider.complete_json(
                model_id=model_id, prompt=redacted, schema=schema
            )
        except TimeoutError:
            parsed, status, meta = None, "TIMEOUT", {}
        except Exception:
            parsed, status, meta = None, "UNKNOWN", {}

        if status == "SUCCESS" and parsed is not None:
            if not validate_against_schema(parsed, schema):
                status = "INVALID_SCHEMA"
                parsed = None

        completed = datetime.now(timezone.utc)
        out_hash = _sha(json.dumps(parsed, sort_keys=True)) if parsed is not None else None
        if status not in ALLOWED_RESULT_STATUS:
            status = "UNKNOWN"
        rec = ProviderRequestRecord(
            provider_id=provider_id,
            model_id=str(meta.get("model_id") or model_id),
            model_version_or_fingerprint=str(meta.get("fingerprint") or model_id),
            role=role,
            request_id=request_id,
            prompt_schema_version=prompt_schema_version,
            prompt_hash=prompt_hash,
            input_hash=input_hash,
            output_hash=out_hash,
            started_at=started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            completed_at=completed.strftime("%Y-%m-%dT%H:%M:%SZ"),
            latency_ms=int((time.perf_counter() - t0) * 1000),
            input_tokens=meta.get("input_tokens"),
            output_tokens=meta.get("output_tokens"),
            retry_count=0,
            rate_limit_state="ok" if status != "RATE_LIMITED" else "limited",
            result_status=status,
        )
        self.records.append(rec)
        # Roles required for future order path fail closed
        order_roles = {"main_market_reasoner", "reflection_reasoner"}
        order_permission = "ALLOW" if status == "SUCCESS" else "BLOCK"
        if role in order_roles and status != "SUCCESS":
            order_permission = "BLOCK"
        return parsed, rec, order_permission


@dataclass
class EnvHttpProvider:
    provider_id: str
    credential_or_url: str

    def complete_json(
        self,
        *,
        model_id: str,
        prompt: str,
        schema: dict[str, Any],
        timeout_s: float = 30.0,
    ) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
        if not self.credential_or_url:
            return None, "PROVIDER_UNAVAILABLE", {"model_id": model_id}
        # Real HTTP not invoked in foundation without explicit opt-in
        if os.getenv("NEXUS_AI_LIVE", "0") != "1":
            return None, "PROVIDER_UNAVAILABLE", {"model_id": model_id, "reason": "live_disabled"}
        return None, "PROVIDER_UNAVAILABLE", {"model_id": model_id}
