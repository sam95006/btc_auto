"""Typed contracts shared by every V18-E provider adapter."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stable_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


GATEWAY_RESPONSE_SCHEMA: dict[str, Any] = {
    "title": "v18_e_gateway_response_v1",
    "required": ["decision", "confidence", "summary", "provider_id"],
    "properties": {
        "decision": {"type": "string"},
        "confidence": {"type": "number"},
        "summary": {"type": "string"},
        "provider_id": {"type": "string"},
        "supporting_evidence_ids": {"type": "array"},
        "contradicting_evidence_ids": {"type": "array"},
        "tool_calls": {"type": "array"},
        "notes": {"type": "array"},
    },
}


@dataclass(frozen=True)
class ToolCallRequest:
    tool_id: str
    args: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"tool_id": self.tool_id, "args": dict(self.args)}


@dataclass(frozen=True)
class GatewayRequest:
    """Typed inbound request — identical shape for all providers."""

    request_id: str
    role: str
    prompt: str
    payload: dict[str, Any]
    schema: dict[str, Any]
    prompt_schema_version: str
    tool_calls: tuple[ToolCallRequest, ...] = ()
    timeout_s: float = 8.0
    max_tokens: int = 1024
    prefer_provider: str | None = None
    cacheable: bool = True

    def fingerprint(self) -> str:
        return stable_hash(
            {
                "role": self.role,
                "prompt": self.prompt,
                "payload": self.payload,
                "schema_title": (self.schema or {}).get("title"),
                "prompt_schema_version": self.prompt_schema_version,
                "tool_calls": [t.to_dict() for t in self.tool_calls],
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "role": self.role,
            "prompt": self.prompt,
            "payload": dict(self.payload),
            "schema": dict(self.schema),
            "prompt_schema_version": self.prompt_schema_version,
            "tool_calls": [t.to_dict() for t in self.tool_calls],
            "timeout_s": self.timeout_s,
            "max_tokens": self.max_tokens,
            "prefer_provider": self.prefer_provider,
            "cacheable": self.cacheable,
            "fingerprint": self.fingerprint(),
        }


@dataclass
class ProviderAttempt:
    provider_id: str
    started_at: str
    completed_at: str | None = None
    latency_ms: int | None = None
    result_status: str = "UNKNOWN"
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GatewayResponse:
    """Typed outbound response — identical shape for all providers."""

    request_id: str
    provider_id: str
    role: str
    result_status: str
    decision: str | None
    confidence: float | None
    summary: str | None
    output: dict[str, Any] | None
    pipeline: str
    capacity_status: str | None
    attempts: list[ProviderAttempt] = field(default_factory=list)
    cache_hit: bool = False
    dedupe_hit: bool = False
    tool_denials: list[str] = field(default_factory=list)
    audit_id: str | None = None
    latency_ms: int | None = None
    busy_loop_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "provider_id": self.provider_id,
            "role": self.role,
            "result_status": self.result_status,
            "decision": self.decision,
            "confidence": self.confidence,
            "summary": self.summary,
            "output": self.output,
            "pipeline": self.pipeline,
            "capacity_status": self.capacity_status,
            "attempts": [a.to_dict() for a in self.attempts],
            "cache_hit": self.cache_hit,
            "dedupe_hit": self.dedupe_hit,
            "tool_denials": list(self.tool_denials),
            "audit_id": self.audit_id,
            "latency_ms": self.latency_ms,
            "busy_loop_count": self.busy_loop_count,
        }


class ProviderAdapter(Protocol):
    """Same typed contract for LOCAL / OPENAI_COMPATIBLE / GROQ / … / FALLBACK."""

    provider_id: str

    def health(self) -> dict[str, Any]:
        """Return {available: bool, status: str, detail: str}."""
        ...

    def complete(
        self,
        request: GatewayRequest,
    ) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
        """Returns (parsed_or_none, result_status, meta)."""
        ...
