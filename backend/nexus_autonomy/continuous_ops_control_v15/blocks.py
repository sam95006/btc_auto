"""Read-only observation blocks for V15-J continuous autonomy ops.

Covers health, storage, Provider capacity, capture health, Decision /
Execution / Reflection lifecycles, Lesson gate, and Qualification blocks.
These blocks never mutate trading state and never write to exchanges.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.continuous_ops_control_v15.constants import (
    PRESERVED_FACTS,
    QUALIFICATION_STAGE_ORDER,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class BlockRegistry:
    """In-memory observation block state for a control session."""

    root: Path
    decision_state: str = "IDLE"
    execution_state: str = "IDLE"
    reflection_state: str = "IDLE"
    lesson_gate_state: str = "CLOSED"
    capture_status: str = "NOT_ATTACHED"
    provider_capacity_status: str = "UNKNOWN"
    provider_tokens_remaining: int = 0
    provider_soft_cap: int = 0
    health_notes: list[str] = field(default_factory=list)
    qualification_stages: dict[str, str] = field(
        default_factory=lambda: {s: "BLOCKED" for s in QUALIFICATION_STAGE_ORDER}
    )

    def health(self, *, control_state: str, kill_engaged: bool) -> dict[str, Any]:
        status = "HEALTHY"
        if kill_engaged:
            status = "KILLED"
        elif control_state in {"BLOCKED"}:
            status = "DEGRADED"
        elif control_state in {"COLD", "STOPPED"}:
            status = "IDLE"
        return {
            "block": "health",
            "status": status,
            "control_state": control_state,
            "kill_engaged": kill_engaged,
            "notes": list(self.health_notes),
            "observed_at": _utc(),
            "exchange_write": False,
            **PRESERVED_FACTS,
        }

    def storage(self) -> dict[str, Any]:
        root = Path(self.root)
        root.mkdir(parents=True, exist_ok=True)
        try:
            usage = shutil.disk_usage(str(root))
            free = int(usage.free)
            total = int(usage.total)
            used = int(usage.used)
            pct_free = (free / total) if total else 0.0
            status = "OK"
            if pct_free < 0.05:
                status = "CRITICAL"
            elif pct_free < 0.10:
                status = "WARN"
        except OSError as exc:
            return {
                "block": "storage",
                "status": "UNAVAILABLE",
                "error": str(exc),
                "observed_at": _utc(),
                "exchange_write": False,
                **PRESERVED_FACTS,
            }
        return {
            "block": "storage",
            "status": status,
            "root": str(root),
            "total_bytes": total,
            "used_bytes": used,
            "free_bytes": free,
            "pct_free": round(pct_free, 6),
            "observed_at": _utc(),
            "exchange_write": False,
            **PRESERVED_FACTS,
        }

    def provider_capacity(self) -> dict[str, Any]:
        remaining = self.provider_tokens_remaining
        soft = self.provider_soft_cap
        if soft <= 0:
            status = "UNCONFIGURED"
        elif remaining <= 0:
            status = "EXHAUSTED"
        elif remaining < soft * 0.1:
            status = "LOW"
        else:
            status = "OK"
        self.provider_capacity_status = status
        return {
            "block": "provider_capacity",
            "status": status,
            "tokens_remaining": remaining,
            "soft_cap": soft,
            "observed_at": _utc(),
            "exchange_write": False,
            "live_provider_call": False,
            **PRESERVED_FACTS,
        }

    def capture_health(self) -> dict[str, Any]:
        return {
            "block": "capture_health",
            "status": self.capture_status,
            "collector_modified": False,
            "live_stop_executed": False,
            "restart_executed": False,
            "observed_at": _utc(),
            "exchange_write": False,
            **PRESERVED_FACTS,
        }

    def decision_lifecycle(self) -> dict[str, Any]:
        return {
            "block": "decision_lifecycle",
            "status": self.decision_state,
            "decorative_intent_ids": False,
            "bound_to_execution": True,
            "observed_at": _utc(),
            "exchange_write": False,
            **PRESERVED_FACTS,
        }

    def execution_lifecycle(self) -> dict[str, Any]:
        return {
            "block": "execution_lifecycle",
            "status": self.execution_state,
            "mode": "SIMULATED_ONLY",
            "exchange_write": False,
            "observed_at": _utc(),
            **PRESERVED_FACTS,
        }

    def reflection_lifecycle(self) -> dict[str, Any]:
        return {
            "block": "reflection_lifecycle",
            "status": self.reflection_state,
            "fabricated_learning": False,
            "observed_at": _utc(),
            "exchange_write": False,
            **PRESERVED_FACTS,
        }

    def lesson_gate(self) -> dict[str, Any]:
        return {
            "block": "lesson_gate",
            "status": self.lesson_gate_state,
            "promotion_allowed": False,
            "observed_at": _utc(),
            "exchange_write": False,
            **PRESERVED_FACTS,
        }

    def qualification_blocks(self) -> dict[str, Any]:
        stages = dict(self.qualification_stages)
        return {
            "block": "qualification_blocks",
            "status": "ALL_BLOCKED",
            "stages": stages,
            "all_blocked": all(v == "BLOCKED" for v in stages.values()),
            "qualification_advanced": False,
            "formal_walk_forward_executed": False,
            "oos_reservation_created": False,
            "oos_executed": False,
            "strategy_promoted": False,
            "observed_at": _utc(),
            "exchange_write": False,
            **PRESERVED_FACTS,
        }

    def all_blocks(self, *, control_state: str, kill_engaged: bool) -> dict[str, Any]:
        return {
            "health": self.health(control_state=control_state, kill_engaged=kill_engaged),
            "storage": self.storage(),
            "provider_capacity": self.provider_capacity(),
            "capture_health": self.capture_health(),
            "decision_lifecycle": self.decision_lifecycle(),
            "execution_lifecycle": self.execution_lifecycle(),
            "reflection_lifecycle": self.reflection_lifecycle(),
            "lesson_gate": self.lesson_gate(),
            "qualification_blocks": self.qualification_blocks(),
        }
