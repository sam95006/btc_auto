"""Audit log for V18-E AI Gateway (append-only in-memory + optional sink)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_ai_gateway_tool_sandbox.contracts import (
    GatewayRequest,
    GatewayResponse,
    utc_now_iso,
)


@dataclass
class AuditEvent:
    audit_id: str
    recorded_at: str
    request: dict[str, Any]
    response: dict[str, Any]
    provider_statuses: dict[str, Any]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "recorded_at": self.recorded_at,
            "request": self.request,
            "response": self.response,
            "provider_statuses": self.provider_statuses,
            "notes": list(self.notes),
        }


@dataclass
class AuditLog:
    events: list[AuditEvent] = field(default_factory=list)

    def record(
        self,
        request: GatewayRequest,
        response: GatewayResponse,
        *,
        provider_statuses: dict[str, Any] | None = None,
        notes: list[str] | None = None,
    ) -> str:
        audit_id = str(uuid.uuid4())
        # Redact prompt secrets lightly — never store raw env-like tokens.
        req = request.to_dict()
        prompt = str(req.get("prompt") or "")
        if "KEY" in prompt.upper() or "SECRET" in prompt.upper():
            req["prompt"] = "[REDACTED_PROMPT]"
        event = AuditEvent(
            audit_id=audit_id,
            recorded_at=utc_now_iso(),
            request=req,
            response=response.to_dict(),
            provider_statuses=dict(provider_statuses or {}),
            notes=list(notes or []),
        )
        self.events.append(event)
        response.audit_id = audit_id
        return audit_id

    def to_list(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.events]
