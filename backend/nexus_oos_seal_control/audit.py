"""Access audit for OOS seal control plane."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.nexus_oos_seal_control.intervals import sha_obj


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class AccessAuditLog:
    events: list[dict[str, Any]] = field(default_factory=list)

    def record(
        self,
        *,
        action: str,
        actor: str,
        allowed: bool,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "seq": len(self.events) + 1,
            "ts": _utc(),
            "action": action,
            "actor": actor,
            "allowed": bool(allowed),
            "detail": detail or {},
        }
        event["event_checksum"] = sha_obj(
            {
                "seq": event["seq"],
                "action": event["action"],
                "actor": event["actor"],
                "allowed": event["allowed"],
                "detail": event["detail"],
            }
        )
        self.events.append(event)
        return event

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_count": len(self.events),
            "events": list(self.events),
            "audit_checksum": sha_obj([e["event_checksum"] for e in self.events]),
            "denied_count": sum(1 for e in self.events if not e["allowed"]),
            "allowed_count": sum(1 for e in self.events if e["allowed"]),
        }

    def reset(self) -> None:
        self.events.clear()
