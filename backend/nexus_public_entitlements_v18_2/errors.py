"""Entitlement denial codes for upgrade gates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EntitlementDenial:
    code: str
    capability_id: str
    current_plan: str
    required_plan: str | None
    message: str
    upgrade_display: str

    def to_response(self) -> tuple[dict[str, Any], int]:
        return (
            {
                "ok": False,
                "error": self.code,
                "capability_id": self.capability_id,
                "current_plan": self.current_plan,
                "required_plan": self.required_plan,
                "message": self.message,
                "upgrade_display": self.upgrade_display,
                "non_execution_disclaimer": True,
                "read_only": True,
            },
            403,
        )
