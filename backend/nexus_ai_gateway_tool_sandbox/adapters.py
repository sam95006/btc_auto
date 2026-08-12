"""Provider adapters sharing one typed GatewayRequest/GatewayResponse contract."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.nexus_ai_gateway_tool_sandbox.constants import PROVIDER_IDS
from backend.nexus_ai_gateway_tool_sandbox.contracts import (
    GATEWAY_RESPONSE_SCHEMA,
    GatewayRequest,
    utc_now_iso,
)


def _validate_minimal(obj: Any, schema: dict[str, Any]) -> bool:
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
        if expected == "array" and not isinstance(val, list):
            return False
        if expected == "object" and not isinstance(val, dict):
            return False
        if expected == "boolean" and not isinstance(val, bool):
            return False
    return True


@dataclass
class BaseAdapter:
    provider_id: str
    available: bool = True
    force_status: str | None = None
    latency_ms: float = 0.0
    default_output: dict[str, Any] = field(default_factory=dict)
    complete_fn: Callable[[GatewayRequest], tuple[dict[str, Any] | None, str, dict[str, Any]]] | None = None

    def health(self) -> dict[str, Any]:
        if self.force_status == "RATE_LIMITED":
            return {"available": False, "status": "RATE_LIMITED", "detail": "forced"}
        if self.force_status == "TIMEOUT":
            return {"available": False, "status": "TIMEOUT", "detail": "forced"}
        if not self.available or self.force_status == "PROVIDER_UNAVAILABLE":
            return {
                "available": False,
                "status": "PROVIDER_UNAVAILABLE",
                "detail": "unavailable",
            }
        return {"available": True, "status": "OK", "detail": "ready"}

    def complete(
        self,
        request: GatewayRequest,
    ) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
        if self.latency_ms > 0:
            time.sleep(min(self.latency_ms / 1000.0, request.timeout_s))
        if self.complete_fn is not None:
            return self.complete_fn(request)

        health = self.health()
        if not health["available"]:
            return None, str(health["status"]), {"model_id": self.provider_id}

        if self.force_status and self.force_status != "SUCCESS":
            return None, self.force_status, {"model_id": self.provider_id}

        # Simulate timeout when configured latency exceeds request budget.
        if self.latency_ms / 1000.0 > request.timeout_s:
            return None, "TIMEOUT", {"model_id": self.provider_id}

        output = dict(self.default_output) if self.default_output else _deterministic_output(
            self.provider_id, request
        )
        output.setdefault("provider_id", self.provider_id)
        schema = request.schema or GATEWAY_RESPONSE_SCHEMA
        if not _validate_minimal(output, schema):
            return None, "INVALID_SCHEMA", {"model_id": self.provider_id}
        return (
            output,
            "SUCCESS",
            {
                "model_id": self.provider_id,
                "input_tokens": max(1, len(request.prompt) // 4),
                "output_tokens": max(1, len(json.dumps(output)) // 4),
                "completed_at": utc_now_iso(),
            },
        )


def _deterministic_output(provider_id: str, request: GatewayRequest) -> dict[str, Any]:
    payload = request.payload or {}
    role = request.role
    if role == "SIMPLE":
        decision = str(payload.get("suggested_decision") or "WAIT")
        conf = float(payload.get("confidence") or 0.55)
        summary = f"deterministic-simple:{provider_id}"
    elif role == "MAJOR_CONTRADICTION_CRITIC":
        decision = str(payload.get("critic_decision") or "ABSTAIN")
        conf = float(payload.get("critic_confidence") or 0.40)
        summary = f"deterministic-critic:{provider_id}"
    else:
        decision = str(payload.get("suggested_decision") or "WAIT")
        conf = float(payload.get("confidence") or 0.60)
        summary = f"deterministic-primary:{provider_id}"
    return {
        "decision": decision,
        "confidence": conf,
        "summary": summary,
        "provider_id": provider_id,
        "supporting_evidence_ids": list(payload.get("supporting_evidence_ids") or []),
        "contradicting_evidence_ids": list(payload.get("contradicting_evidence_ids") or []),
        "tool_calls": [],
        "notes": [],
    }


@dataclass
class DeterministicFallbackAdapter(BaseAdapter):
    """Always-available local deterministic responder — never calls network."""

    provider_id: str = "DETERMINISTIC_FALLBACK"
    available: bool = True

    def health(self) -> dict[str, Any]:
        return {"available": True, "status": "OK", "detail": "deterministic_always_on"}

    def complete(
        self,
        request: GatewayRequest,
    ) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
        output = _deterministic_output(self.provider_id, request)
        return (
            output,
            "SUCCESS",
            {
                "model_id": "deterministic_v1",
                "input_tokens": 0,
                "output_tokens": 0,
                "completed_at": utc_now_iso(),
                "deterministic": True,
            },
        )


@dataclass
class LocalAdapter(BaseAdapter):
    provider_id: str = "LOCAL"


@dataclass
class OpenAICompatibleAdapter(BaseAdapter):
    provider_id: str = "OPENAI_COMPATIBLE"

    def health(self) -> dict[str, Any]:
        if os.getenv("NEXUS_OPENAI_COMPAT_BASE_URL") or self.available:
            return super().health()
        return {
            "available": False,
            "status": "PROVIDER_UNAVAILABLE",
            "detail": "missing_base_url",
        }


@dataclass
class GroqAdapter(BaseAdapter):
    provider_id: str = "GROQ"

    def health(self) -> dict[str, Any]:
        # Live HTTP is opt-in; fixtures/tests use available flag / force_status.
        if self.force_status or not self.available:
            return super().health()
        if os.getenv("NEXUS_AI_LIVE", "0") == "1" and not (
            os.getenv("GROQ_API_KEY_PRIMARY") or os.getenv("GROQ_API_KEY")
        ):
            return {
                "available": False,
                "status": "PROVIDER_UNAVAILABLE",
                "detail": "missing_key",
            }
        return super().health()


@dataclass
class SambaNovaAdapter(BaseAdapter):
    provider_id: str = "SAMBANOVA"

    def health(self) -> dict[str, Any]:
        if self.force_status or not self.available:
            return super().health()
        if os.getenv("NEXUS_AI_LIVE", "0") == "1" and not os.getenv("SAMBANOVA_API_KEY"):
            return {
                "available": False,
                "status": "PROVIDER_UNAVAILABLE",
                "detail": "missing_key",
            }
        return super().health()


@dataclass
class OtherApprovedProviderAdapter(BaseAdapter):
    provider_id: str = "OTHER_APPROVED_PROVIDER"


def build_default_adapters(
    *,
    mock: bool = True,
    unavailable: frozenset[str] | None = None,
) -> dict[str, BaseAdapter]:
    """Construct the six founder-required providers under one contract."""
    down = unavailable or frozenset()
    adapters: dict[str, BaseAdapter] = {
        "LOCAL": LocalAdapter(available="LOCAL" not in down),
        "OPENAI_COMPATIBLE": OpenAICompatibleAdapter(
            available="OPENAI_COMPATIBLE" not in down
        ),
        "GROQ": GroqAdapter(available="GROQ" not in down),
        "SAMBANOVA": SambaNovaAdapter(available="SAMBANOVA" not in down),
        "OTHER_APPROVED_PROVIDER": OtherApprovedProviderAdapter(
            available="OTHER_APPROVED_PROVIDER" not in down
        ),
        "DETERMINISTIC_FALLBACK": DeterministicFallbackAdapter(),
    }
    if not mock:
        # Non-mock still keeps DETERMINISTIC_FALLBACK; remote adapters stay
        # unavailable unless NEXUS_AI_LIVE=1 and credentials exist.
        for pid in ("OPENAI_COMPATIBLE", "GROQ", "SAMBANOVA", "OTHER_APPROVED_PROVIDER"):
            if pid not in down:
                adapters[pid].available = os.getenv("NEXUS_AI_LIVE", "0") == "1"
    assert set(adapters) == set(PROVIDER_IDS)
    return adapters


def provider_status_matrix(adapters: dict[str, BaseAdapter]) -> dict[str, dict[str, Any]]:
    return {pid: adapters[pid].health() for pid in PROVIDER_IDS if pid in adapters}
